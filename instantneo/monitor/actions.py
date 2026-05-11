"""Actions built-in para Monitor.

Cada función es un **factory** que recibe parámetros y devuelve un
``Callable[[History], None]`` (la action). Las actions tienen efectos:
pueden appendear entries al History (in-band) o producir side effects
externos (out-of-band, ej. HTTP, archivos).

Doc rector: ``docs/design/monitor-design.md`` (sección "Actions
built-in (in-band)").

Set mínimo: solo ``stop_signal`` y ``append_note``. El resto (notify
slack, persist to disk, llamadas a otros agentes, etc.) son funciones
custom del usuario — viven en recipes/docs, no en el core.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from instantneo.history.queries import current_origin, current_run_id

if TYPE_CHECKING:
    from instantneo.history.history import History
    from instantneo.monitor.monitor import Action


def stop_signal(text: str) -> "Action":
    """Action factory: appendea un ``stop_signal`` con el texto dado.

    El entry resultante tiene::

        Entry(
            author="orchestrator",
            type="stop_signal",
            content={
                "text":   text,
                "origin": current_origin(history),    # None si no hay
                "run_id": current_run_id(history),    # None si no hay
            },
        )

    El Loop, si lo escucha (vía su parámetro ``stop_signals=[..., text, ...]``),
    rompe el run con ``stop_reason=text``. Los campos ``origin`` y
    ``run_id`` no son para el matching del Loop — son para auditoría
    posterior. El Loop **solo compara** ``content["text"]`` con su
    whitelist.

    Args:
        text: identificador de la señal de parada. Debe estar en la
            whitelist ``stop_signals`` de algún Loop que comparta el
            History para tener efecto en cierre de loop. Si nadie lo
            escucha, queda como entry informativa.
    """
    def action(history: "History") -> None:
        history.append(
            author="orchestrator",
            type="stop_signal",
            content={
                "text":   text,
                "origin": current_origin(history),
                "run_id": current_run_id(history),
            },
        )
    return action


def append_note(text: str, author: str = "orchestrator") -> "Action":
    """Action factory: appendea una entry ``type="note"`` con el texto dado.

    Utilidad genérica para dejar marcas en el History (checkpoints,
    eventos relevantes, notas de auditoría). Las vistas pueden o no
    incluir las notes en su output; el agente típicamente no las ve.

    Args:
        text: contenido de la nota.
        author: identificador del autor. Default ``"orchestrator"``.
    """
    def action(history: "History") -> None:
        history.append(
            author=author,
            type="note",
            content={"text": text},
        )
    return action
