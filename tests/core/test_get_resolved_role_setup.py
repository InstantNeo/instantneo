"""
Tests de ``InstantNeo.get_resolved_role_setup`` (PR 6).

Doc rector: docs/design/log-design.md líneas 1275-1276 (Pre-requisito 3).

Cubre dos cosas:
1. El método produce el string esperado en varios escenarios.
2. PARIDAD con ``_prepare_messages``: el system message del flow real
   coincide con lo que devuelve este método. Esa es la garantía de
   que el refactor no cambió comportamiento.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo import InstantNeo, AgentCapabilities, tool


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

@tool(description="Get weather", parameters={
    "location": {"description": "City", "type": "str"},
})
def get_weather(location: str) -> dict:
    return {"location": location}


def _mk_agent(role_setup="Sos un asistente.", with_tools=False,
              with_tool_instructions=False):
    kwargs = dict(
        provider="openai", model="gpt-5-mini", api_key="sk-test",
        role_setup=role_setup,
    )
    if with_tools:
        caps = AgentCapabilities(skills=[get_weather])
        if with_tool_instructions:
            caps.set_global_instructions(
                "\n\n## Tools disponibles\nUsá get_weather para clima."
            )
        kwargs["tools"] = caps
    return InstantNeo(**kwargs)


# ════════════════════════════════════════════════════════════════════
# Casos directos del método
# ════════════════════════════════════════════════════════════════════

def test_only_role_setup_no_extras() -> None:
    agent = _mk_agent("Hola soy un agente.")
    result = agent.get_resolved_role_setup()
    assert result == "Hola soy un agente."


def test_with_tool_instructions_appended() -> None:
    """Cuando AgentCapabilities tiene `global_instructions`, esas se
    convierten en `tool_instructions` y se pegan al role_setup.
    (Comportamiento heredado de _prepare_messages.)"""
    agent = _mk_agent("Sos un asistente.",
                      with_tools=True, with_tool_instructions=True)
    result = agent.get_resolved_role_setup()
    assert result.startswith("Sos un asistente.")
    assert "Tools disponibles" in result   # del global_instructions
    assert "get_weather" in result


def test_with_tools_but_no_global_instructions_only_role_setup() -> None:
    """Si el agente tiene tools pero AgentCapabilities no tiene
    global_instructions, tool_instructions queda vacío y el resolved
    es solo el role_setup."""
    agent = _mk_agent("Sos un asistente.",
                      with_tools=True, with_tool_instructions=False)
    result = agent.get_resolved_role_setup()
    assert result == "Sos un asistente."


def test_with_shelf_context_appended() -> None:
    agent = _mk_agent("Hola.")
    result = agent.get_resolved_role_setup(shelf_context="Datos extra.")
    assert "Hola." in result
    assert "ACTIVE KNOWLEDGE" in result
    assert "Datos extra." in result


def test_with_tools_and_shelf_context() -> None:
    """Combinación: role + tool_instructions + shelf, en ese orden."""
    agent = _mk_agent("Asistente.",
                      with_tools=True, with_tool_instructions=True)
    result = agent.get_resolved_role_setup(shelf_context="Memoria activa.")
    # Asistente al inicio
    assert result.startswith("Asistente.")
    # Tools en el medio
    assert "Tools disponibles" in result
    # Memoria activa al final, dentro del bloque
    assert "Memoria activa." in result
    # Orden: Asistente < Tools < Memoria
    assert result.find("Asistente.") < result.find("Tools disponibles") < result.find("Memoria activa.")


def test_empty_role_setup_returns_empty_string() -> None:
    """Si role_setup es '' o None, el método no crashea, devuelve ''
    cuando no hay nada que agregar."""
    agent = InstantNeo(
        provider="openai", model="gpt-5-mini", api_key="sk-test",
        role_setup="",  # vacío
    )
    assert agent.get_resolved_role_setup() == ""


def test_shelf_context_none_equivalent_to_no_arg() -> None:
    agent = _mk_agent("Hola.")
    a = agent.get_resolved_role_setup()
    b = agent.get_resolved_role_setup(shelf_context=None)
    assert a == b


# ════════════════════════════════════════════════════════════════════
# Paridad con _prepare_messages — garantiza no-regresión
# ════════════════════════════════════════════════════════════════════

def test_parity_with_prepare_messages_basic() -> None:
    """El system message de `_prepare_messages` coincide con
    `get_resolved_role_setup`."""
    agent = _mk_agent("Hola.")
    messages = agent._prepare_messages("user prompt")
    system_msg = messages[0]
    assert system_msg["role"] == "system"
    assert system_msg["content"] == agent.get_resolved_role_setup()


def test_parity_with_prepare_messages_with_shelf() -> None:
    agent = _mk_agent("Hola.")
    messages = agent._prepare_messages("user prompt", shelf_context="Datos.")
    system_msg = messages[0]
    assert system_msg["content"] == agent.get_resolved_role_setup(shelf_context="Datos.")


def test_parity_with_prepare_messages_with_tools_and_shelf() -> None:
    agent = _mk_agent("Asistente.",
                      with_tools=True, with_tool_instructions=True)
    messages = agent._prepare_messages("hola", shelf_context="Memoria.")
    system_msg = messages[0]
    assert system_msg["content"] == agent.get_resolved_role_setup(shelf_context="Memoria.")


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("only_role_setup_no_extras",              test_only_role_setup_no_extras),
        ("with_tool_instructions_appended",        test_with_tool_instructions_appended),
        ("with_tools_but_no_global_instructions_only_role_setup",
         test_with_tools_but_no_global_instructions_only_role_setup),
        ("with_shelf_context_appended",            test_with_shelf_context_appended),
        ("with_tools_and_shelf_context",           test_with_tools_and_shelf_context),
        ("empty_role_setup_returns_empty_string",  test_empty_role_setup_returns_empty_string),
        ("shelf_context_none_equivalent_to_no_arg", test_shelf_context_none_equivalent_to_no_arg),
        ("parity_with_prepare_messages_basic",     test_parity_with_prepare_messages_basic),
        ("parity_with_prepare_messages_with_shelf", test_parity_with_prepare_messages_with_shelf),
        ("parity_with_prepare_messages_with_tools_and_shelf", test_parity_with_prepare_messages_with_tools_and_shelf),
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print()
    total = len(tests)
    print(f"PASS: {total - len(failures)} / {total}")
    if failures:
        sys.exit(1)
