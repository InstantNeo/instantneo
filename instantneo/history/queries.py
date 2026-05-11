"""Helpers de query sobre un History.

Las 4 queries devuelven información del **run actual** asumiendo la
convención del Loop:

- ``current_run_config``: lee la entry ``type="run_start"`` más reciente.
- ``current_run_id``: shortcut sobre ``current_run_config``.
- ``current_origin``: shortcut sobre ``current_run_config``.
- ``current_step_num``: lee la entry ``type="step_start"`` más reciente.

Spec autoritativa: ``docs/design/loop-design.md`` sección "Helpers
necesarios" (líneas 1267-1294).

**Por qué basadas en `run_start`/`step_start`**: son las entries que el
Loop emite al inicio de cada run/step con la metadata canónica. Otras
entries (response, tool_call, error) pueden tener ``content["origin"]``
y ``content["run_id"]`` también (los populariza el bridge), pero la
verdad del **run actual** está en ``run_start``. Escanear cualquier
entry tiene el riesgo de devolver datos de un run anterior cuando el
History acumula multi-run.

**Limitación de uso** (cita del doc línea 1293):
> "Estos helpers funcionan correctamente en uso secuencial (un solo
> loop.run() activo a la vez sobre un History dado). Para escenarios
> concurrentes (dos Loops escribiendo al mismo History en paralelo),
> retornarían el último run_start que esté presente, que puede no ser
> el del Loop que invoca. Concurrencia real queda fuera de scope para
> v1; cuando se implemente, los helpers deberán recibir contexto
> explícito o usar contextvars."

Sin Loop ni entries ``run_start`` (ej. History manual sin orquestador),
todas las queries devuelven ``None``. Es degradación esperada.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from instantneo.history.history import History


def current_run_config(history: "History") -> Optional[dict]:
    """Devuelve el ``content`` de la entry ``run_start`` más reciente.

    Útil para que conditions/actions del Monitor accedan a la cabecera
    del run actual sin escarbar manualmente.

    Devuelve ``None`` si no hay ninguna entry de tipo ``run_start``.
    """
    starts = history.by_type("run_start")
    return starts[-1].content if starts else None


def current_run_id(history: "History") -> Optional[str]:
    """Devuelve el ``run_id`` del ``run_start`` más reciente, o ``None``."""
    cfg = current_run_config(history)
    if cfg is None:
        return None
    return cfg.get("run_id")


def current_origin(history: "History") -> Optional[str]:
    """Devuelve el ``origin`` del ``run_start`` más reciente, o ``None``.

    Útil para auditoría: "¿qué orquestador produjo este run?".
    """
    cfg = current_run_config(history)
    if cfg is None:
        return None
    return cfg.get("origin")


def current_step_num(history: "History") -> Optional[int]:
    """Devuelve el ``step_num`` del ``step_start`` más reciente, o ``None``.

    Asume que el Loop appendea entries ``type="step_start"`` con
    ``content["step_num"]: int``. Si esa convención no se cumple,
    devuelve ``None`` sin crashear.

    Lo necesitan conditions tipo ``every_n_steps``.
    """
    steps = history.by_type("step_start")
    if not steps:
        return None
    sn = steps[-1].content.get("step_num") if isinstance(steps[-1].content, dict) else None
    if not isinstance(sn, int):
        return None
    return sn
