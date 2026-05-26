"""``InstantLoop`` — orquestador event-sourced (PR 8 del v2).

Doc rector: ``docs/design/loop-design.md`` entero.

Compone todas las piezas anteriores del v2:

- ``History`` (PR 2) para registrar entries operacionales.
- ``Monitor`` (PR 3) que el Loop invoca post-bridge cada step.
- Queries (PR 5) para que actions del Monitor conozcan el run actual.
- Bridge (PR 5) para descomponer ``RunInfo`` en entries.
- ``RunInfo.run_params`` completo + ``reasoning_tokens`` (PR 4).
- ``agent.get_resolved_role_setup()`` + ``capabilities.get_schemas()`` (PR 6).
- ``TurnLog`` y ``RunLog`` (PR 7 + this PR Capa 2) cuando ``debug=True``.

El flujo per-step sigue exactamente la spec de
``loop-design.md`` líneas 1014-1263.
"""
from __future__ import annotations

import datetime
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Union

from instantneo.history import History
from instantneo.history.from_run_info import append_entry_from_run
from instantneo.monitor import Monitor, MonitorOperations
from instantneo.monitor.actions import stop_signal
from instantneo.monitor.conditions import when_last_tool_called
from instantneo.debug import TurnLog, build_agent_config
from instantneo.loop.debug import RunLog, _new_run_log_for_loop
from instantneo.loop.default_view import (
    RenderedPrompt, _build_loop_default_view,
)


# ════════════════════════════════════════════════════════════════════
# Excepciones
# ════════════════════════════════════════════════════════════════════

class LoopConfigError(ValueError):
    """Error de configuración del InstantLoop al construir."""


# ════════════════════════════════════════════════════════════════════
# RunResult
# ════════════════════════════════════════════════════════════════════

@dataclass
class RunResult:
    """Resultado de ``loop.run()``. Metadata + dos punteros (History + Log).

    Doc: ``docs/design/loop-design.md`` líneas 109-138.
    """
    history: History
    name: str
    run_id: str
    terminated_reason: str          # "stop_signal" | "view" | "external" | "max_steps" | "error"
    stop_reason: Optional[str]      # string específico, None si max_steps/error
    duration_s: float
    total_steps: int
    log: Optional[RunLog] = None    # populado si debug=True


# ════════════════════════════════════════════════════════════════════
# Helpers locales
# ════════════════════════════════════════════════════════════════════

def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _refs_from(images: Union[str, list, None]) -> Optional[list]:
    """Convierte el arg ``images`` (str | list[str] | None) a list[dict] refs.

    Shape canónico: ``[{"source": "url_or_path"}, ...]`` que la
    vista ``loop_default`` consume.
    """
    if images is None:
        return None
    if isinstance(images, str):
        images = [images]
    return [{"source": img} for img in images]


def _resolve_monitors(monitors) -> Monitor:
    """Idem al patrón de InstantNeo(tools=...):

    - ``None`` → ``Monitor()`` vacío.
    - ``Monitor`` instance → la misma instancia (mutaciones se propagan).
    - ``list[Monitor]`` → ``MonitorOperations.union(*monitors)`` (snapshot).
    """
    if monitors is None:
        return Monitor()
    if isinstance(monitors, Monitor):
        return monitors
    if isinstance(monitors, (list, tuple)):
        return MonitorOperations.union(*monitors)
    raise LoopConfigError(
        f"monitors debe ser Monitor, list[Monitor] o None — got {type(monitors).__name__}"
    )


def _resolve_stop_tool(stop_tool) -> Optional[list[str]]:
    """Normaliza stop_tool a lista de strings o None."""
    if stop_tool is None:
        return None
    if isinstance(stop_tool, str):
        return [stop_tool]
    if isinstance(stop_tool, (list, tuple)):
        return [str(s) for s in stop_tool]
    raise LoopConfigError(
        f"stop_tool debe ser str, list[str] o None — got {type(stop_tool).__name__}"
    )


# ════════════════════════════════════════════════════════════════════
# InstantLoop
# ════════════════════════════════════════════════════════════════════

class InstantLoop:
    """Orquestador event-sourced que corre un ``InstantNeo`` en N steps."""

    def __init__(
        self,
        *,
        agent,                                              # InstantNeo
        history: Optional[History] = None,
        name: Optional[str] = None,
        monitors: Union[Monitor, list, None] = None,
        view: str = "loop_default",
        max_steps: int = 30,
        stop_signals: Optional[list[str]] = None,
        stop_tool: Union[str, list[str], None] = None,
        debug: bool = False,
        debug_base_path: Union[str, Path, None] = None,
    ):
        # Validar max_steps
        if not isinstance(max_steps, int) or isinstance(max_steps, bool):
            raise LoopConfigError(f"max_steps debe ser int, got {type(max_steps).__name__}")
        if max_steps < 0:
            raise LoopConfigError(f"max_steps debe ser >= 0 (0 = sin cap); got {max_steps}")

        self.agent = agent
        self.history = history if history is not None else History()
        self.name = name or f"loop_{uuid.uuid4().hex[:8]}"
        self.max_steps = max_steps

        # Transformar "loop_default" al nombre único de este loop.
        # Cada loop registra su propia vista con origin baked-in, evitando
        # colisiones en multi-loop concurrente sobre el mismo History.
        # El user siempre puede pasar view="loop_default" y obtiene el
        # comportamiento esperado, con nombre interno "loop_default_{name}".
        if view == "loop_default":
            self.view = f"loop_default_{self.name}"
        else:
            self.view = view
        self.debug = bool(debug)

        # Stop signals: whitelist provista + auto del sugar
        signals = list(stop_signals) if stop_signals else []

        # Stop tool: sugar. Cada nombre se convierte en:
        # - "agent called <name>" en la whitelist
        # - rule en el monitor: when_last_tool_called(name) → stop_signal("agent called <name>")
        self.stop_tool: Optional[list[str]] = _resolve_stop_tool(stop_tool)
        sugar_monitor = Monitor(name="_stop_tool_sugar")
        if self.stop_tool:
            for tool_name in self.stop_tool:
                signal_text = f"agent called {tool_name}"
                if signal_text not in signals:
                    signals.append(signal_text)
                sugar_monitor.add_rule(
                    when_last_tool_called(tool_name),
                    stop_signal(signal_text),
                )

        self.stop_signals: list[str] = signals

        # Monitor: combinar el del user con el del sugar
        user_monitor = _resolve_monitors(monitors)
        if self.stop_tool:
            self.monitor = MonitorOperations.union(
                user_monitor, sugar_monitor, name=f"{self.name}_combined",
            )
        else:
            self.monitor = user_monitor

        # Estado interno (reset en cada .run())
        self._run_counter = 0
        self._current_run_id: Optional[str] = None
        self._stop_requested = False
        self._stop_request_reason: Optional[str] = None
        self._run_start_entry_id = 0

        # Path base para debug logs
        self._debug_base_path = Path(debug_base_path) if debug_base_path else Path("debug_output")

        # Registrar la vista si no existe ya en el History
        self._ensure_view_available()

    # ── Setup ──────────────────────────────────────────────────────

    def _ensure_view_available(self) -> None:
        """Garantiza que ``self.view`` existe en el History.

        Para la vista default, el nombre ya fue transformado a
        ``"loop_default_{self.name}"`` en ``__init__``. Cada loop
        registra su propia vista con ``origin`` baked-in — sin
        colisión entre loops que comparten el mismo History.

        Para vistas custom (cualquier nombre que no empiece con
        ``"loop_default_"``), el user es responsable de registrarlas
        antes de construir el Loop.
        """
        if self.history.has_view(self.view):
            return  # ya registrada (este mismo loop en un run anterior)

        if self.view.startswith("loop_default_"):
            # Vista default de este loop: registrar con origin baked-in.
            self.history.add_view(
                self.view,
                _build_loop_default_view(origin=self.name),
            )
        else:
            raise LoopConfigError(
                f"Vista '{self.view}' no registrada en el History. "
                f"Registrala antes de construir el Loop, o usá la default 'loop_default'."
            )

    # ── Acceso externo: cancelar ───────────────────────────────────

    def stop(self, reason: str = "external") -> None:
        """Cancela el run en curso desde código externo.

        Setea un flag interno; el Loop rompe al final del step actual
        con ``terminated_reason="external"`` y ``stop_reason=reason``.
        No toca el History.
        """
        self._stop_requested = True
        self._stop_request_reason = reason

    # ── Ejecución ──────────────────────────────────────────────────

    def run(
        self,
        prompt: str,
        *,
        images: Union[str, list[str], None] = None,
        image_detail: Optional[str] = None,
    ) -> RunResult:
        """Ejecuta el loop hasta que alguna condición de stop dispare.

        Doc: loop-design.md líneas 1014-1263.
        """
        run_id = uuid.uuid4().hex
        self._current_run_id = run_id
        self._stop_requested = False
        self._stop_request_reason = None
        started_at = time.time()
        started_at_iso = datetime.datetime.fromtimestamp(
            started_at, tz=datetime.timezone.utc,
        ).isoformat()
        terminated_reason: Optional[str] = None
        stop_reason: Optional[str] = None
        total_steps = 0

        # 0. Construir RunLog si debug=True
        log: Optional[RunLog] = None
        if self.debug:
            self._run_counter += 1
            log = _new_run_log_for_loop(
                loop_name=self.name,
                sequence_num=self._run_counter,
                run_id=run_id,
                started_at_iso=started_at_iso,
                config=self._build_full_config(prompt, images, image_detail),
                base_path=self._debug_base_path,
            )
            log.write_config()

        # 1. Vista (ya está garantizada por _ensure_view_available)
        # 2. Emitir run_start
        self.history.append(
            author="orchestrator",
            type="run_start",
            content=self._build_run_start_content(run_id, started_at_iso),
        )

        # 3. Emitir prompt del user
        self.history.append(
            author="user",
            type="prompt",
            content={
                "text": prompt,
                "images": _refs_from(images),
                "image_detail": image_detail,
                "origin": self.name,
                "run_id": run_id,
            },
        )

        # 3.b Snapshot del último id para freshness filter de stop_signals
        all_entries = self.history.all()
        self._run_start_entry_id = all_entries[-1].id if all_entries else 0

        # 4. Loop de steps
        step_num = 0
        while True:
            step_num += 1
            if self.max_steps != 0 and step_num > self.max_steps:
                terminated_reason = "max_steps"
                total_steps = step_num - 1
                break

            step_start_time = time.perf_counter()

            # 4.a Render vista
            rendered = self.history.export(self.view)

            if isinstance(rendered, RenderedPrompt):
                if rendered.stop_reason:
                    terminated_reason = "view"
                    stop_reason = rendered.stop_reason
                    total_steps = step_num - 1
                    break
                text_to_send = rendered.text
                images_to_send = rendered.images
                image_detail_to_send = rendered.image_detail
            elif isinstance(rendered, str):
                text_to_send = rendered
                images_to_send = None
                image_detail_to_send = None
            else:
                raise TypeError(
                    f"View '{self.view}' devolvió {type(rendered).__name__}, "
                    f"esperado: str o RenderedPrompt"
                )

            # 4.b step_start
            step_started_iso = _utcnow_iso()
            self.history.append(
                author="orchestrator",
                type="step_start",
                content={
                    "origin": self.name,
                    "run_id": run_id,
                    "step_num": step_num,
                },
            )

            # 4.c agent.run() — captura excepciones que el agente no haya
            # registrado en run_info.error
            try:
                self._invoke_agent(text_to_send, images_to_send, image_detail_to_send)
            except Exception as e:
                last_run = getattr(self.agent, "last_run", None)
                if last_run is None or getattr(last_run, "error", None) is None:
                    self.history.append(
                        author="orchestrator",
                        type="error",
                        content={
                            "origin": self.name,
                            "run_id": run_id,
                            "step_num": step_num,
                            "exception": str(e),
                            "exception_type": type(e).__name__,
                            "context": "agent.run",
                        },
                    )
                    terminated_reason = "error"
                    total_steps = step_num
                    break

            # 4.d Bridge
            if getattr(self.agent, "last_run", None) is not None:
                append_entry_from_run(
                    self.history,
                    self.agent.last_run,
                    turn_num=step_num,
                    author=getattr(self.agent, "name", None) or "agent",
                    origin=self.name,
                    run_id=run_id,
                )

                # 4.e Si debug, append TurnLog al RunLog
                if log is not None:
                    turn = TurnLog.from_runinfo(
                        step_num=step_num,
                        started_at=step_started_iso,
                        completed_at=_utcnow_iso(),
                        run_info=self.agent.last_run,
                    )
                    log.append_turn(turn)

            # 4.f Invocar Monitor (puede appendear stop_signal entries)
            try:
                self.monitor(self.history)
            except Exception as e:
                self.history.append(
                    author="orchestrator",
                    type="error",
                    content={
                        "origin": self.name,
                        "run_id": run_id,
                        "step_num": step_num,
                        "exception": str(e),
                        "exception_type": type(e).__name__,
                        "context": "monitor_action",
                    },
                )
                terminated_reason = "error"
                total_steps = step_num
                break

            # 4.g step_end
            self.history.append(
                author="orchestrator",
                type="step_end",
                content={
                    "origin": self.name,
                    "run_id": run_id,
                    "step_num": step_num,
                    "duration_ms": (time.perf_counter() - step_start_time) * 1000,
                },
            )

            # 4.h Vía Monitor / append externo — stop_signal fresca
            signal = self._find_fresh_stop_signal()
            if signal is not None:
                terminated_reason = "stop_signal"
                stop_reason = signal.content.get("text")
                total_steps = step_num
                break

            # 4.i Vía externa — flag loop.stop()
            if self._stop_requested:
                terminated_reason = "external"
                stop_reason = self._stop_request_reason
                total_steps = step_num
                break

            total_steps = step_num

        # 5. run_end siempre
        completed_at = time.time()
        completed_at_iso = datetime.datetime.fromtimestamp(
            completed_at, tz=datetime.timezone.utc,
        ).isoformat()
        self.history.append(
            author="orchestrator",
            type="run_end",
            content={
                "origin": self.name,
                "run_id": run_id,
                "completed_at": completed_at_iso,
                "duration_s": completed_at - started_at,
                "terminated_reason": terminated_reason,
                "stop_reason": stop_reason,
                "total_steps": total_steps,
            },
        )

        # 6. Cerrar RunLog si aplica
        if log is not None:
            log.completed_at = completed_at_iso
            log.terminated_reason = terminated_reason
            log.stop_reason = stop_reason
            log.write_run_end()

        return RunResult(
            history=self.history,
            name=self.name,
            run_id=run_id,
            terminated_reason=terminated_reason or "max_steps",
            stop_reason=stop_reason,
            duration_s=completed_at - started_at,
            total_steps=total_steps,
            log=log,
        )

    # ── Internals ──────────────────────────────────────────────────

    def _invoke_agent(self, text: str, images, image_detail) -> None:
        """Llama ``agent.run()``. Separado para que tests puedan mockear."""
        self.agent.run(text, images=images, image_detail=image_detail)

    def _find_fresh_stop_signal(self):
        """Devuelve la primera entry stop_signal appendeada después del
        run start cuyo text matchea con self.stop_signals. None si no hay.
        """
        if not self.stop_signals:
            return None
        signals_set = set(self.stop_signals)
        for e in self.history.all():
            if e.id <= self._run_start_entry_id:
                continue
            if e.type != "stop_signal":
                continue
            if isinstance(e.content, dict) and e.content.get("text") in signals_set:
                return e
        return None

    def _build_run_start_content(self, run_id: str, started_at_iso: str) -> dict:
        """Construye el content de la entry run_start.

        Doc: loop-design.md líneas 854-897.
        """
        return {
            "origin": self.name,
            "run_id": run_id,
            "started_at": started_at_iso,
            "agent": build_agent_config(self.agent),
            "loop": {
                "name": self.name,
                "max_steps": self.max_steps,
                "view": self.view,
                "stop_signals": list(self.stop_signals),
                "stop_tool": list(self.stop_tool) if self.stop_tool else None,
                "debug": self.debug,
            },
        }

    def _build_full_config(self, prompt, images, image_detail) -> dict:
        """Config completo (agent + loop + input) para el RunLog.

        Doc: log-design.md líneas 250-294.
        """
        return {
            "agent": build_agent_config(self.agent),
            "loop": {
                "name": self.name,
                "max_steps": self.max_steps,
                "view": self.view,
                "stop_signals": list(self.stop_signals),
                "stop_tool": list(self.stop_tool) if self.stop_tool else None,
                "debug": self.debug,
            },
            "input": {
                "prompt": prompt,
                "images": _refs_from(images),
                "image_detail": image_detail,
            },
        }


__all__ = [
    "InstantLoop",
    "RunResult",
    "LoopConfigError",
]
