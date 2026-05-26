"""Capa Loop — ``InstantLoop`` v2 + ``RunLog`` Capa 2 + vista default.

Re-exporta las piezas públicas:

- ``InstantLoop``: orquestador event-sourced.
- ``RunResult``: resultado de ``loop.run()``.
- ``RenderedPrompt``: tipo de retorno de las vistas para multimodal.
- ``RunLog``: aggregator de debug (Capa 2 del sistema de logging).

Documentación de diseño: ``docs/design/loop-design.md`` y
``docs/design/log-design.md``.
"""
from instantneo.loop.instant_loop import (
    InstantLoop, RunResult, LoopConfigError,
)
from instantneo.loop.default_view import RenderedPrompt, loop_default
from instantneo.loop.debug import RunLog, load_run_logs

__all__ = [
    "InstantLoop",
    "RunResult",
    "RenderedPrompt",
    "RunLog",
    "load_run_logs",
    "loop_default",
    "LoopConfigError",
]
