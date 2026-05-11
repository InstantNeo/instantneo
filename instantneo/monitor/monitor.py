"""Monitor: rule engine standalone que opera contra un ``History``.

Doc rector: ``docs/design/monitor-design.md``.

Reglas que sostienen el diseño (resumidas):

- **Standalone**: el Monitor no guarda referencia a ningún History. El
  history llega como argumento cada vez que se invoca.
- **Pasivo**: no tiene reloj interno, no observa autónomamente. Hace
  algo solo cuando alguien lo llama (``monitor(history)``).
- **Reusable**: la misma instancia puede invocarse contra múltiples
  Histories.
- **Síncrono**: las acciones bloquean la invocación. Si una action
  quiere correr en background, arma su propio thread.
- **Genérico**: no sabe del Loop ni de InstantNeo. Su única dependencia
  es la interface ``History``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from instantneo.history.history import History


# Type aliases públicos.
Condition = Callable[["History"], bool]
Action = Callable[["History"], None]


class Monitor:
    """Rule engine: lista de (condition, action) que se evalúa contra un History.

    Uso típico::

        monitor = Monitor()
        monitor.add_rule(when_type_present("error"), stop_signal("err"))
        monitor.add_rule(every_n_steps(10), append_note("checkpoint"))

        monitor(history)        # una pasada — evalúa todas las rules
    """

    def __init__(self, name: Optional[str] = None) -> None:
        """Construye un Monitor vacío.

        Args:
            name: opcional, útil para debug / identificación. None por default.
        """
        self.name = name
        self._rules: list[tuple[Condition, Action]] = []

    def add_rule(self, when: Condition, do: Action) -> None:
        """Añade una regla ``(when, do)`` al final de la lista.

        No valida que ``when`` y ``do`` sean callables — Python falla en
        invocación si no lo son. Mantiene la API mínima.
        """
        self._rules.append((when, do))

    def __call__(self, history: "History") -> None:
        """Itera reglas en orden de registro; dispara las que matchean.

        Cada acción bloquea hasta terminar. Las acciones posteriores
        ven el estado dejado por las anteriores en la misma pasada
        (porque el History es append-only y todas las rules leen del
        mismo objeto).

        No captura excepciones — si una action levanta, propaga.
        """
        for when, do in self._rules:
            if when(history):
                do(history)


class MonitorOperations:
    """Utilidades estáticas para componer monitors."""

    @staticmethod
    def union(*monitors: Monitor, name: Optional[str] = None) -> Monitor:
        """Combina N monitors en uno nuevo, preservando orden de reglas.

        El monitor resultante tiene las reglas de cada input concatenadas
        en orden. **No muta los inputs** — copia las listas.

        Si no se pasa ningún monitor, devuelve un Monitor vacío.
        """
        merged = Monitor(name=name)
        for m in monitors:
            for when, do in m._rules:
                merged.add_rule(when, do)
        return merged
