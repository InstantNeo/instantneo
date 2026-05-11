"""History: log event-sourced inmutable y append-only para InstantLoop v2.

Define la unidad de dato ``Entry`` (frozen dataclass) y el container
``History``, agnóstico al dominio: no sabe de agentes, loops ni prompts.
Solo guarda, devuelve y permite registrar vistas (funciones puras que
proyectan el log para un consumidor concreto).

Documentación de diseño: ``docs/design/history-design.md``.

Sin Monitor adentro, sin emisión de eventos, sin validación de ``type``
o ``content``. Solo storage + registry de vistas.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# Type alias público para vistas. Cualquier callable que reciba un
# History entero y devuelva algo. El tipo de retorno es libre — texto,
# lista, dict, objeto custom, lo que el consumidor necesite.
View = Callable[["History"], Any]


@dataclass(frozen=True)
class Entry:
    """Unidad de dato del History. Inmutable una vez creada.

    Los campos los provee el caller excepto ``id`` y ``timestamp``, que
    los asigna ``History.append()``.

    Atributos:
        id: auto-incremental desde 1, asignado por History.
        author: identificador libre de quién la creó.
        timestamp: cuándo se appendeó (epoch seconds); overrideable.
        type: clase de entry, string arbitrario (sin validación).
        content: dict libre. Su shape lo decide el productor.
        refs: tuple de ids de OTRAS entries que esta referencia/cubre.
    """

    id: int
    author: str
    timestamp: float
    type: str
    content: dict = field(default_factory=dict)
    refs: tuple[int, ...] = ()

    def to_dict(self) -> dict:
        """Serialización JSON-safe del entry.

        ``refs`` se serializa como lista (JSON no tiene tuple). Para
        ``content``, si contiene tipos no estándar (datetime, set, etc.),
        cada uno se convierte a string vía ``default=str`` durante
        ``json.dumps``. Esto evita errores de serialización pero hace que
        el roundtrip no preserve esos tipos exactamente (vuelve como
        string). Es comportamiento intencional — el History no valida
        ni transforma ``content``, solo serializa defensivamente.
        """
        # Validar serializabilidad de content sin perder el tipo en el
        # dict resultante: si content es JSON-safe, queda intacto; si
        # no, se sustituye por su versión stringificada vía json
        # roundtrip con default=str.
        try:
            json.dumps(self.content)
            content_safe: Any = self.content
        except TypeError:
            content_safe = json.loads(json.dumps(self.content, default=str))

        return {
            "id":        self.id,
            "author":    self.author,
            "timestamp": self.timestamp,
            "type":      self.type,
            "content":   content_safe,
            "refs":      list(self.refs),
        }


class History:
    """Storage append-only de Entries + registro de vistas.

    Pasivo: no emite eventos, no notifica, no tiene observers, no tiene
    Monitor adentro. Solo guarda y devuelve.

    Uso típico:

        >>> from instantneo.history import History
        >>> history = History()
        >>> history.append(author="user", type="message", content={"text": "hola"})
        Entry(id=1, ...)
        >>> history.all()
        [Entry(id=1, ...)]
    """

    def __init__(self, name: Optional[str] = None) -> None:
        """Construye un History vacío.

        Args:
            name: opcional, útil para debug / multi-history. None por default.
        """
        self.name = name
        self._entries: list[Entry] = []
        self._views: dict[str, View] = {}
        self._next_id: int = 1

    # ── Storage ────────────────────────────────────────────────────

    def append(
        self,
        *,
        author: str,
        type: str,
        content: dict,
        refs: tuple[int, ...] = (),
        timestamp: Optional[float] = None,
    ) -> Entry:
        """Appendea una nueva entry y retorna la entry creada.

        El ``id`` se asigna auto-incremental (no overrideable). El
        ``timestamp`` por default es ``time.time()``, overrideable
        vía kwarg para casos de import histórico o replay determinista.
        """
        entry_id = self._next_id
        self._next_id += 1
        entry = Entry(
            id=entry_id,
            author=author,
            timestamp=timestamp if timestamp is not None else time.time(),
            type=type,
            content=content,
            refs=tuple(refs),
        )
        self._entries.append(entry)
        return entry

    def get(self, id: int) -> Entry:
        """Devuelve la entry con el id pedido. Levanta ``KeyError`` si no existe."""
        for entry in self._entries:
            if entry.id == id:
                return entry
        raise KeyError(f"Entry id={id} no existe en este History")

    def all(self) -> list[Entry]:
        """Lista de todas las entries en orden de id ascendente.

        Retorna una copia: mutar la lista resultante no afecta al History.
        """
        return list(self._entries)

    def by_author(self, author: str) -> list[Entry]:
        """Entries cuyo author coincide. Devuelve lista vacía si no hay match."""
        return [e for e in self._entries if e.author == author]

    def by_type(self, type: str) -> list[Entry]:
        """Entries cuyo type coincide. Devuelve lista vacía si no hay match."""
        return [e for e in self._entries if e.type == type]

    # ── Registry de vistas ──────────────────────────────────────────

    def view(self, name: str) -> Callable[[View], View]:
        """Decorator para registrar una vista.

        Es azúcar sobre ``add_view`` — internamente llama
        ``self.add_view(name, fn)``. Retorna la función original
        (no envuelta), por lo que sigue siendo invocable directamente.

            >>> @history.view("my_view")
            ... def my_view(h):
            ...     return [e.content for e in h.all()]
        """
        def decorator(fn: View) -> View:
            self.add_view(name, fn)
            return fn
        return decorator

    def add_view(self, name: str, fn: View) -> None:
        """Registra una vista por nombre. Sobreescribe si ya existía."""
        self._views[name] = fn

    def export(self, name: str) -> Any:
        """Ejecuta la vista registrada con este History como argumento.

        Levanta ``KeyError`` si no hay vista con ese nombre.
        """
        if name not in self._views:
            raise KeyError(f"Vista '{name}' no registrada en este History")
        return self._views[name](self)

    def list_views(self) -> list[str]:
        """Lista de nombres de vistas registradas."""
        return list(self._views.keys())

    def has_view(self, name: str) -> bool:
        """True si hay una vista con ese nombre registrada."""
        return name in self._views

    # ── Serialización ───────────────────────────────────────────────

    def to_dicts(self) -> list[dict]:
        """Lista de dicts (uno por entry, producido por ``Entry.to_dict()``)."""
        return [e.to_dict() for e in self._entries]

    def to_json(self) -> str:
        """JSON string con todas las entries.

        Roundtrip-safe junto con ``History.from_dicts(json.loads(s))``.
        """
        return json.dumps(self.to_dicts(), default=str)

    @classmethod
    def from_dicts(cls, dicts: list[dict], name: Optional[str] = None) -> "History":
        """Reconstruye un History desde la salida de ``to_dicts()``.

        Restaura ``refs`` como tuple. Los ``id`` y ``timestamp`` se
        respetan tal cual venían (no se reasignan). El contador interno
        de ``id`` se ajusta a ``max(ids) + 1`` para que futuros
        ``append`` no colisionen.

        Si ``dicts`` está vacío, retorna un History vacío con
        ``_next_id = 1``.
        """
        history = cls(name=name)
        max_id = 0
        for d in dicts:
            entry = Entry(
                id=d["id"],
                author=d["author"],
                timestamp=d["timestamp"],
                type=d["type"],
                content=d.get("content", {}),
                refs=tuple(d.get("refs", ())),
            )
            history._entries.append(entry)
            if entry.id > max_id:
                max_id = entry.id
        history._next_id = max_id + 1
        return history

    # ── Reset ──────────────────────────────────────────────────────

    def reset(self) -> None:
        """Borra todas las entries y reinicia el contador de id.

        Operación irreversible. Las refs de cualquier entry futura no
        podrán apuntar a las antiguas. Patrón seguro: persistir ANTES
        (e.g. ``Path("snapshot.json").write_text(history.to_json())``).

        Las vistas registradas se preservan — son metadata del History,
        no contenido.
        """
        self._entries = []
        self._next_id = 1
