"""Vista por defecto del Loop + ``RenderedPrompt``.

Doc rector: ``docs/design/loop-design.md`` sección "Vista loop_default"
(líneas 665-842).

``loop_default(history, *, show_all_runs=False, image_policy="every_turn")``
es la vista que el agente recibe como prompt en cada turno. Es
deliberadamente simple: filtra por run_id actual, muestra solo
entries narrativas (``prompt``, ``response``, ``tool_call``), agrupa
por turno, formatea markdown, decide qué imágenes enviar.

Devuelve un ``RenderedPrompt`` con texto + (opcionalmente) imágenes +
posible ``stop_reason`` (mecanismo opt-in para que la vista corte el
loop antes de gastar el agente).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional

from instantneo.history.queries import (
    current_run_id, current_run_config,
)

if TYPE_CHECKING:
    from instantneo.history import History, Entry


# ════════════════════════════════════════════════════════════════════
# RenderedPrompt
# ════════════════════════════════════════════════════════════════════

@dataclass
class RenderedPrompt:
    """Output de una Vista del Loop.

    El Loop, al recibir un ``RenderedPrompt``, hace
    ``agent.run(text, images=..., image_detail=...)`` con lo que la vista
    indique. Si una vista custom devuelve solo ``str``, el Loop manda
    ``text`` sin imágenes.

    Atributos:
        text: texto markdown que va al provider como prompt del turno.
        images: paths/URLs a pasar a ``agent.run(images=...)``. None
            para no enviar imágenes.
        image_detail: idem ``image_detail`` de InstantNeo.
        stop_reason: si está set, el Loop rompe ANTES de invocar al
            agente, con ``terminated_reason="view"`` y este texto.
    """
    text: str
    images: Optional[list] = None
    image_detail: Optional[str] = None
    stop_reason: Optional[str] = None


# ════════════════════════════════════════════════════════════════════
# Formatter — markdown del historial
# ════════════════════════════════════════════════════════════════════

def _format_json(obj: Any) -> str:
    """JSON pretty-print defensivo (default=str para tipos exóticos)."""
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return repr(obj)


def _format_image_refs(entry_content: dict) -> str:
    """Texto que menciona las imágenes adjuntas sin embeber binarios.

    Las refs vienen como ``[{"source": "url_o_path", ...}, ...]``.
    """
    imgs = entry_content.get("images") or []
    if not imgs:
        return ""
    sources = []
    for i, ref in enumerate(imgs, start=1):
        if isinstance(ref, dict):
            sources.append(ref.get("source", f"img_{i}"))
        else:
            sources.append(str(ref))
    return f"_imágenes adjuntas: {', '.join(sources)}_"


def _markdown_format_default(
    entries: list,
    *,
    current_step: int,
    max_steps: Any,
) -> str:
    """Construye el texto markdown a partir de las entries filtradas.

    Estructura:

        Estás en el turno N de M.

        <historial>
        ## Turno 1
        [user]: <prompt>
        _imágenes adjuntas: ..._   (si hubo)
        ### reasoning
        <reasoning si existe>
        ### assistant:
        <response.text>
        ### tool_call: name
        arguments:
        {...}
        result:
        {...}
        </historial>
    """
    lines: list[str] = []

    # Header con turno actual
    if max_steps == 0 or max_steps is None:
        lines.append(f"Estás en el turno {current_step}.")
    else:
        lines.append(f"Estás en el turno {current_step} de {max_steps}.")
        if isinstance(max_steps, int) and current_step >= max_steps:
            lines.append("\n**Aviso: este es el último turno. Tenés que concluir ahora.**")
    lines.append("")
    lines.append("<historial>")

    # Agrupar por step_num — el step_num vive en `turn_num` de las entries del bridge.
    by_step: dict[int, list] = {}
    prompt_entries: list = []
    for e in entries:
        content = e.content if isinstance(e.content, dict) else {}
        if e.type == "prompt":
            prompt_entries.append(e)
            continue
        # bridge mete turn_num en content
        step = content.get("turn_num", 0)
        by_step.setdefault(step, []).append(e)

    # Mostrar prompts del user. En el caso típico (filtrado por run_id
    # actual) habrá solo uno; con show_all_runs=True pueden ser varios.
    for i, p in enumerate(prompt_entries, start=1):
        text = p.content.get("text", "")
        header = "## Inicio" if i == 1 and len(prompt_entries) == 1 else f"## Inicio (run #{i})"
        lines.append(header)
        lines.append(f"[user]: {text}")
        img_text = _format_image_refs(p.content)
        if img_text:
            lines.append(img_text)
        lines.append("")

    # Por cada step (ordenado)
    for step_num in sorted(by_step.keys()):
        lines.append(f"## Turno {step_num}")
        for e in by_step[step_num]:
            c = e.content if isinstance(e.content, dict) else {}
            if e.type == "response":
                reasoning = c.get("reasoning")
                if reasoning:
                    lines.append("### reasoning")
                    lines.append(str(reasoning))
                text = c.get("text") or ""
                lines.append("### assistant:")
                lines.append(text)
            elif e.type == "tool_call":
                name = c.get("name", "<unknown>")
                lines.append(f"### tool_call: {name}")
                args = c.get("arguments")
                if args is not None:
                    lines.append("arguments:")
                    lines.append("```json")
                    lines.append(_format_json(args))
                    lines.append("```")
                result = c.get("result")
                if result is not None:
                    lines.append("result:")
                    lines.append("```json")
                    lines.append(_format_json(result))
                    lines.append("```")
                exc = c.get("exception")
                if exc:
                    lines.append(f"_exception_: `{exc}`")
        lines.append("")

    lines.append("</historial>")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# loop_default — la vista
# ════════════════════════════════════════════════════════════════════

def loop_default(
    history: "History",
    *,
    show_all_runs: bool = False,
    image_policy: Literal["every_turn", "first_only", "none"] = "every_turn",
    origin: Optional[str] = None,
) -> RenderedPrompt:
    """Vista default del Loop. Texto markdown + imágenes según policy.

    Doc: docs/design/loop-design.md sección "Implementación" (línea 690).

    Comportamiento de texto:
      - Si ``origin`` está set: filtra por ``content["origin"] == origin``.
        Muestra todos los runs de ese loop. Concurrent-safe para multi-loop.
      - Si ``show_all_runs=True``: muestra todo el History sin filtro.
      - Default (sin origin, sin show_all_runs): filtra por run_id actual
        (comportamiento legacy, correcto para loop único).
      - Solo incluye entries narrativas: prompt, response, tool_call.
      - Renderea reasoning del response (extended thinking) como bloque
        distinguible.
      - Renderea tool args/results como JSON pretty.
      - Agrupa por turno con header inicial y warning de último turno.

    Comportamiento de imágenes:
      Las imágenes viven en la entry ``prompt`` del run actual con
      ``content["images"]: list[dict]`` donde cada dict tiene ``"source"``.
      Esta vista las incluye en el ``RenderedPrompt`` según ``image_policy``:

        - "every_turn" (default): incluye en cada step.
        - "first_only":           solo en step 1.
        - "none":                 nunca.

    Args:
        origin: nombre del loop (``loop.name``). Cuando está set, filtra
            por ``content["origin"]`` en vez de por run_id — correcto en
            escenarios multi-loop concurrentes. El Loop lo bake-a en el
            closure al registrar la vista, así que el user no lo pasa
            directamente salvo en vistas custom.
    """
    # ── Determinar modo de filtrado ────────────────────────────────
    if show_all_runs:
        entries = [
            e for e in history.all()
            if e.type in {"prompt", "response", "tool_call"}
        ]
        cfg = current_run_config(history) or {}
        current_rid = None
        run_step_starts = history.by_type("step_start")

    elif origin is not None:
        # Multi-loop: filtrar por origin (concurrent-safe).
        # Muestra todos los runs de este loop.
        entries = [
            e for e in history.all()
            if isinstance(e.content, dict)
            and e.content.get("origin") == origin
            and e.type in {"prompt", "response", "tool_call"}
        ]
        # Para max_steps y current_step: leer del último run_start de este origin.
        origin_run_starts = [
            e for e in history.by_type("run_start")
            if isinstance(e.content, dict) and e.content.get("origin") == origin
        ]
        cfg = origin_run_starts[-1].content if origin_run_starts else {}
        current_rid = cfg.get("run_id")
        run_step_starts = [
            e for e in history.by_type("step_start")
            if isinstance(e.content, dict)
            and e.content.get("origin") == origin
            and e.content.get("run_id") == current_rid
        ]

    else:
        # Legacy: un solo loop. Filtrar por run_id actual.
        rid = current_run_id(history)
        entries = [
            e for e in history.all()
            if isinstance(e.content, dict)
            and e.content.get("run_id") == rid
            and e.type in {"prompt", "response", "tool_call"}
        ]
        cfg = current_run_config(history) or {}
        current_rid = rid
        run_step_starts = [
            e for e in history.by_type("step_start")
            if isinstance(e.content, dict) and e.content.get("run_id") == rid
        ]

    # ── Header: turno actual y máximo ─────────────────────────────
    max_steps = cfg.get("loop", {}).get("max_steps", "?")

    # `current_step` = step que está por ejecutarse.
    # El Loop appendea `step_start` DESPUÉS de invocar la vista, así que
    # contamos los step_starts ya presentes y sumamos 1.
    current_step = len(run_step_starts) + 1

    text = _markdown_format_default(
        entries,
        current_step=current_step,
        max_steps=max_steps,
    )

    # ── Imágenes: prompt del run actual ───────────────────────────
    images, image_detail = None, None
    prompt_entry = next(
        (e for e in entries
         if e.type == "prompt"
         and isinstance(e.content, dict)
         and e.content.get("run_id") == current_rid),
        None,
    )
    if prompt_entry and prompt_entry.content.get("images"):
        send_now = (
            image_policy == "every_turn"
            or (image_policy == "first_only" and current_step == 1)
        )
        if send_now:
            refs = prompt_entry.content["images"]
            images = [
                (img["source"] if isinstance(img, dict) else str(img))
                for img in refs
            ]
            image_detail = prompt_entry.content.get("image_detail")

    return RenderedPrompt(text=text, images=images, image_detail=image_detail)


# ════════════════════════════════════════════════════════════════════
# Helper para registrar la vista en un History
# ════════════════════════════════════════════════════════════════════

def _build_loop_default_view(origin: Optional[str] = None) -> Callable:
    """Devuelve una callable que el Loop registra como vista default.

    Cuando ``origin`` está set (caso normal — el Loop lo pasa siempre),
    la vista resultante filtra por ese origin: concurrent-safe para
    multi-loop. Sin origin, usa el fallback legacy por run_id.

    Args:
        origin: ``loop.name`` del Loop que registra la vista. El Loop
            lo pasa siempre al construirse; solo es None si se llama
            desde código externo sin loop (uso avanzado).
    """
    if origin is not None:
        return lambda h: loop_default(h, origin=origin)
    return loop_default


__all__ = [
    "RenderedPrompt",
    "loop_default",
    "_build_loop_default_view",
    "_markdown_format_default",
]
