"""Conditions built-in para Monitor.

Cada función es un **factory** que recibe parámetros y devuelve un
``Callable[[History], bool]`` (la condition). Las conditions son
**puras**: misma history → mismo bool. Sin side effects.

Doc rector: ``docs/design/monitor-design.md`` (secciones "Conditions
built-in" y "Combinadores").
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from instantneo.history.history import History
    from instantneo.monitor.monitor import Condition


# ════════════════════════════════════════════════════════════════════
# Conditions sobre cantidad y tipo
# ════════════════════════════════════════════════════════════════════

def when_entry_count_above(n: int) -> "Condition":
    """True cuando el total de entries en el History supera ``n``."""
    def cond(history: "History") -> bool:
        return len(history.all()) > n
    return cond


def when_type_count_above(type: str, n: int) -> "Condition":
    """True cuando la cantidad de entries del ``type`` dado supera ``n``."""
    def cond(history: "History") -> bool:
        return len(history.by_type(type)) > n
    return cond


def when_author_count_above(author: str, n: int) -> "Condition":
    """True cuando la cantidad de entries del ``author`` dado supera ``n``."""
    def cond(history: "History") -> bool:
        return len(history.by_author(author)) > n
    return cond


def when_type_present(type: str) -> "Condition":
    """True cuando hay al menos una entry de ese ``type`` en el History."""
    def cond(history: "History") -> bool:
        return len(history.by_type(type)) > 0
    return cond


# ════════════════════════════════════════════════════════════════════
# Conditions sobre la última entry
# ════════════════════════════════════════════════════════════════════

def when_last_is_type(type: str) -> "Condition":
    """True cuando la última entry del History tiene ese ``type``.

    Devuelve ``False`` si el History está vacío.
    """
    def cond(history: "History") -> bool:
        entries = history.all()
        if not entries:
            return False
        return entries[-1].type == type
    return cond


def when_last_is_author(author: str) -> "Condition":
    """True cuando la última entry del History es de ese ``author``.

    Devuelve ``False`` si el History está vacío.
    """
    def cond(history: "History") -> bool:
        entries = history.all()
        if not entries:
            return False
        return entries[-1].author == author
    return cond


def when_last_content_matches(predicate: Callable[[dict], bool]) -> "Condition":
    """True cuando el ``content`` de la última entry cumple el ``predicate``.

    Devuelve ``False`` si el History está vacío. Si el predicado mismo
    falla, la excepción propaga (es bug del predicado, no del helper).
    """
    def cond(history: "History") -> bool:
        entries = history.all()
        if not entries:
            return False
        return bool(predicate(entries[-1].content))
    return cond


def when_last_tool_called(name: str) -> "Condition":
    """True cuando la última entry ``tool_call`` tiene ``content["name"] == name``.

    Útil para el patrón "parar cuando el agente llamó tal tool". Es la
    base del sugar ``stop_tool`` en ``InstantLoop``.

    Devuelve ``False`` si no hay entries ``tool_call`` aún en el History,
    o si la última tool_call fue una distinta.

    Args:
        name: nombre exacto de la tool (case-sensitive).
    """
    def cond(history: "History") -> bool:
        tool_calls = history.by_type("tool_call")
        if not tool_calls:
            return False
        last = tool_calls[-1]
        return last.content.get("name") == name
    return cond


# ════════════════════════════════════════════════════════════════════
# Condition sobre tokens (asume vista registrada)
# ════════════════════════════════════════════════════════════════════

def when_tokens_above(
    view_name: str,
    n: int,
    tokenizer: Optional[Callable[[str], int]] = None,
) -> "Condition":
    """True cuando el output de ``history.export(view_name)`` supera ``n`` tokens.

    Args:
        view_name: nombre de una vista registrada en el History. Debe
            devolver un string. Si la vista no existe, ``export`` levanta
            ``KeyError`` cuando la condition se evalúe.
        n: umbral en tokens.
        tokenizer: opcional. Función ``str -> int``. Default: estimación
            por longitud de chars dividida por 4 (aproximación razonable
            para texto en inglés/español sin uso intensivo de tokens
            multi-byte). Pasale uno preciso si te importa la exactitud
            (e.g. ``tiktoken.get_encoding("cl100k_base").encode``).
    """
    if tokenizer is None:
        def default_tokenizer(s: str) -> int:
            return len(s) // 4
        tokenizer = default_tokenizer

    def cond(history: "History") -> bool:
        output = history.export(view_name)
        return tokenizer(output) > n
    return cond


# ════════════════════════════════════════════════════════════════════
# Conditions sobre steps (asume convención del Loop)
#
# El Loop appendea entries `type="step_start"` con `content["step_num"]`.
# Si no usás un Loop con esa convención, estas conditions devuelven False.
# ════════════════════════════════════════════════════════════════════

def _last_step_num(history: "History") -> Optional[int]:
    """Devuelve el step_num de la última entry tipo step_start, o None."""
    entries = history.by_type("step_start")
    if not entries:
        return None
    last = entries[-1]
    step_num = last.content.get("step_num") if isinstance(last.content, dict) else None
    if not isinstance(step_num, int):
        return None
    return step_num


def every_n_steps(n: int) -> "Condition":
    """True cuando el último ``step_num`` es múltiplo de ``n``.

    Requiere que el Loop appendea entries ``type="step_start"`` con
    ``content["step_num"]: int``. Sin esa convención devuelve ``False``
    siempre.

    ``step_num = 0`` se considera múltiplo de cualquier ``n`` (False
    matemáticamente para algunos n; aquí devolvemos False también para
    evitar confusión: la "primera pasada" no debería disparar la rule).
    """
    def cond(history: "History") -> bool:
        step_num = _last_step_num(history)
        if step_num is None or step_num <= 0:
            return False
        return step_num % n == 0
    return cond


def at_step(k: int) -> "Condition":
    """True cuando el último ``step_num`` es exactamente ``k``.

    Misma convención que ``every_n_steps``: depende de que el Loop
    emita entries de tipo ``step_start`` con ``content["step_num"]``.
    """
    def cond(history: "History") -> bool:
        return _last_step_num(history) == k
    return cond


# ════════════════════════════════════════════════════════════════════
# Combinadores
# ════════════════════════════════════════════════════════════════════

def And(*conds: "Condition") -> "Condition":
    """Compuesta: todas las conditions deben evaluar a True.

    Con cero conditions devuelve ``True`` (cuantificador universal sobre
    conjunto vacío). Cortocircuita en la primera False.
    """
    def cond(history: "History") -> bool:
        for c in conds:
            if not c(history):
                return False
        return True
    return cond


def Or(*conds: "Condition") -> "Condition":
    """Compuesta: al menos una condition debe evaluar a True.

    Con cero conditions devuelve ``False`` (cuantificador existencial
    sobre conjunto vacío). Cortocircuita en la primera True.
    """
    def cond(history: "History") -> bool:
        for c in conds:
            if c(history):
                return True
        return False
    return cond


def Not(c: "Condition") -> "Condition":
    """La negación de una condition."""
    def cond(history: "History") -> bool:
        return not c(history)
    return cond
