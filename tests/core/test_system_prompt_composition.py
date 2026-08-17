"""
Tests de composición del system prompt en ``_prepare_messages``.

Regresión de A1 (revisión de seguridad, docs/security-architecture-review.md):
el guard era ``if self.config.role_setup:`` mientras que el contenido lo
compone ``get_resolved_role_setup()`` a partir de tres fuentes
(role_setup + tool_instructions + shelf_context). Con ``role_setup=""``
pero capabilities con ``global_instructions``, el mensaje ``system`` no se
agregaba y todo se perdía en silencio.

Doblemente importante porque ``get_resolved_role_setup()`` es lo que
``build_agent_config()`` persiste en el RunLog: la divergencia hacía que
el log forense registrara un system prompt que nunca se envió.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo import InstantNeo, AgentCapabilities, tool


@tool(description="Consulta el clima", parameters={
    "location": {"description": "Ciudad", "type": "str"},
})
def get_weather(location: str) -> dict:
    return {"location": location}


def _mk_agent(role_setup, global_instructions=None):
    kwargs = dict(
        provider="openai", model="gpt-5-mini", api_key="sk-test",
        role_setup=role_setup,
    )
    if global_instructions is not None:
        caps = AgentCapabilities(skills=[get_weather])
        caps.set_global_instructions(global_instructions)
        kwargs["tools"] = caps
    return InstantNeo(**kwargs)


def _system_of(messages):
    return next((m["content"] for m in messages if m["role"] == "system"), None)


# ────────────────────────────────────────────────────────────────────

def test_global_instructions_sobreviven_sin_role_setup() -> None:
    """El caso exacto de A1, que es además el patrón que recomienda el README."""
    agent = _mk_agent(role_setup="", global_instructions="\n\nUsá get_weather para clima.")
    messages = agent._prepare_messages("hola")

    system = _system_of(messages)
    assert system is not None, "se perdió el mensaje system"
    assert "get_weather" in system


def test_shelf_context_sobrevive_sin_role_setup() -> None:
    agent = _mk_agent(role_setup="")
    messages = agent._prepare_messages("hola", None, "MEMORIA ACTIVA")

    system = _system_of(messages)
    assert system is not None
    assert "MEMORIA ACTIVA" in system


def test_paridad_con_get_resolved_role_setup_sin_role_setup() -> None:
    """Fidelidad del RunLog: lo enviado == lo que reporta la introspección."""
    agent = _mk_agent(role_setup="", global_instructions="\n\nInstrucciones de tools.")
    messages = agent._prepare_messages("hola", None, "MEMORIA")

    assert _system_of(messages) == agent.get_resolved_role_setup("MEMORIA")


def test_paridad_con_role_setup_presente() -> None:
    """No-regresión del camino que ya funcionaba."""
    agent = _mk_agent(role_setup="Sos un asistente.", global_instructions="\n\nTools.")
    messages = agent._prepare_messages("hola", None, "MEMORIA")

    assert _system_of(messages) == agent.get_resolved_role_setup("MEMORIA")


def test_sin_nada_que_componer_no_hay_system() -> None:
    """Un agente sin role_setup ni instrucciones ni shelf no manda system vacío."""
    agent = _mk_agent(role_setup="")
    messages = agent._prepare_messages("hola")

    assert _system_of(messages) is None
    assert [m["role"] for m in messages] == ["user"]


TESTS = [
    ("global_instructions_sin_role_setup", test_global_instructions_sobreviven_sin_role_setup),
    ("shelf_context_sin_role_setup", test_shelf_context_sobrevive_sin_role_setup),
    ("paridad_sin_role_setup", test_paridad_con_get_resolved_role_setup_sin_role_setup),
    ("paridad_con_role_setup", test_paridad_con_role_setup_presente),
    ("sin_nada_no_hay_system", test_sin_nada_que_componer_no_hay_system),
]


if __name__ == "__main__":
    for name, fn in TESTS:
        fn()
        print(f"  OK  {name}")
    print(f"\n{len(TESTS)} tests pasaron.")
