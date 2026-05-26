"""Capa History — log event-sourced inmutable y append-only.

Re-exporta las dos piezas públicas de este sub-paquete:

- ``Entry``: la unidad de dato (frozen dataclass).
- ``History``: el container con storage + registro de vistas.

Documentación de diseño: ``docs/design/history-design.md``.
"""
from instantneo.history.history import Entry, History

__all__ = ["Entry", "History"]
