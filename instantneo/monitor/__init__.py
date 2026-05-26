"""Capa Monitor — rule engine standalone para InstantLoop v2.

Re-exporta las piezas públicas principales:

- ``Monitor``: rule engine genérico que opera contra un ``History``.
- ``MonitorOperations``: utilidades para combinar varios monitors.

Conditions y actions built-in viven en sub-módulos importables vía
``from instantneo.monitor.conditions import when_*`` y
``from instantneo.monitor.actions import stop_signal, append_note``.

Documentación de diseño: ``docs/design/monitor-design.md``.
"""
from instantneo.monitor.monitor import Monitor, MonitorOperations

__all__ = ["Monitor", "MonitorOperations"]
