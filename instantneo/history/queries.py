"""Helpers de query sobre un History.

Este módulo crece a lo largo de los PRs del v2. En el PR 3 entran solo
las dos queries que la action built-in ``stop_signal`` necesita
(``current_origin`` y ``current_run_id``). En el PR 5 se agregarán
``current_run_config`` y ``current_step_num`` cuando el bridge y el
Loop emitan las entries operacionales correspondientes.

Los helpers degradan limpio: si el History no tiene entries con los
campos esperados, devuelven ``None``. No crashean cuando se invocan
contra histories sin Loop ni bridge — solo no producen información.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from instantneo.history.history import History


def current_origin(history: "History") -> Optional[str]:
    """Última `origin` registrada en ``content["origin"]`` de alguna entry.

    Escanea de la entry más reciente a la más antigua y devuelve la
    primera `origin` encontrada. Si ninguna entry tiene el campo,
    devuelve ``None``.

    Quién popula este campo: el bridge (PR 5) lo agrega a las entries
    derivadas de un ``RunInfo``. Si llamás esta función contra un
    History sin entries del bridge, vas a obtener ``None`` — esperado.
    """
    for entry in reversed(history.all()):
        origin = entry.content.get("origin") if isinstance(entry.content, dict) else None
        if origin is not None:
            return origin
    return None


def current_run_id(history: "History") -> Optional[str]:
    """Último `run_id` registrado en ``content["run_id"]`` de alguna entry.

    Mismo patrón que ``current_origin``: scan en orden inverso, primer
    match gana, ``None`` si no hay ninguno.
    """
    for entry in reversed(history.all()):
        run_id = entry.content.get("run_id") if isinstance(entry.content, dict) else None
        if run_id is not None:
            return run_id
    return None
