"""
Tests transversales después del PR 6 (cross PR 2 + PR 5 + PR 6).

Verifican que los nuevos métodos públicos
(``agent.capabilities.get_schemas()`` y ``agent.get_resolved_role_setup()``)
producen data utilizable por el orquestador / bridge / RunLog:

- El snapshot puede serializarse a History via Entries.
- Un orquestador puede armar un ``run_start`` self-contained con esos
  artefactos.
- Sobrevive el roundtrip JSON.

Dual-mode. Sin LLM ni red.
"""
import sys
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo import InstantNeo, AgentCapabilities, tool
from instantneo.history import History
from instantneo.history.queries import current_run_config


@tool(description="Get weather", parameters={
    "location": {"description": "City", "type": "str"},
})
def get_weather(location: str) -> dict:
    return {"location": location, "temp": 22}


def _mk_agent(role_setup="Sos un asistente útil.", with_tools=True,
              with_global_instructions=True):
    kwargs = dict(
        provider="openai", model="gpt-5-mini", api_key="sk-test",
        role_setup=role_setup,
    )
    if with_tools:
        caps = AgentCapabilities(skills=[get_weather])
        if with_global_instructions:
            caps.set_global_instructions("\n\nUsá get_weather si necesitás clima.")
        kwargs["tools"] = caps
    return InstantNeo(**kwargs)


# ════════════════════════════════════════════════════════════════════
# Serializable: los outputs son JSON-safe
# ════════════════════════════════════════════════════════════════════

def test_get_schemas_output_is_json_serializable() -> None:
    """Cada schema producido es JSON-safe (importante para logs)."""
    agent = _mk_agent()
    schemas = agent.capabilities.get_schemas()
    # json.dumps no debe fallar
    serialized = json.dumps(schemas)
    deserialized = json.loads(serialized)
    assert deserialized == schemas


def test_get_resolved_role_setup_is_plain_string() -> None:
    """El resolved es siempre str, JSON-safe trivialmente."""
    agent = _mk_agent()
    result = agent.get_resolved_role_setup()
    assert isinstance(result, str)
    # roundtrip
    assert json.loads(json.dumps(result)) == result


# ════════════════════════════════════════════════════════════════════
# Cross PR 2 + PR 6: el snapshot se guarda en una entry y sobrevive
# ════════════════════════════════════════════════════════════════════

def test_agent_snapshot_persists_in_history_entry() -> None:
    """Caso de uso real: un orquestador captura schemas + role_setup
    resolved en una entry tipo `run_start`, y eso sobrevive el roundtrip."""
    agent = _mk_agent(role_setup="Soy un experto.")

    h = History()
    h.append(
        author="orchestrator",
        type="run_start",
        content={
            "origin": "test_loop",
            "run_id": "run-001",
            "agent": {
                "provider": "openai",
                "model": "gpt-5-mini",
                "role_setup":          agent.config.role_setup,
                "role_setup_resolved": agent.get_resolved_role_setup(),
                "tools":               agent.capabilities.get_schemas(),
            },
            "loop": {"max_steps": 20},
        },
    )

    # Roundtrip
    h2 = History.from_dicts(json.loads(h.to_json()))
    restored = h2.all()[0]
    agent_info = restored.content["agent"]

    assert agent_info["provider"] == "openai"
    assert agent_info["role_setup_resolved"].startswith("Soy un experto.")
    assert len(agent_info["tools"]) == 1
    assert agent_info["tools"][0]["function"]["name"] == "get_weather"


# ════════════════════════════════════════════════════════════════════
# Cross PR 5 + PR 6: queries leen del run_start con snapshot real
# ════════════════════════════════════════════════════════════════════

def test_current_run_config_returns_agent_snapshot() -> None:
    """Después de que un orquestador emite run_start con el snapshot
    real, las queries del PR 5 lo recuperan correctamente."""
    agent = _mk_agent()
    h = History()
    h.append(
        author="orchestrator",
        type="run_start",
        content={
            "origin": "loop_X",
            "run_id": "run-X1",
            "agent": {
                "tools":               agent.capabilities.get_schemas(),
                "role_setup_resolved": agent.get_resolved_role_setup(),
            },
        },
    )

    cfg = current_run_config(h)
    assert cfg is not None
    assert cfg["origin"] == "loop_X"
    assert len(cfg["agent"]["tools"]) == 1
    assert "get_weather" in cfg["agent"]["role_setup_resolved"] or \
           "asistente" in cfg["agent"]["role_setup_resolved"].lower()


# ════════════════════════════════════════════════════════════════════
# Refactor no rompió el flow: _prepare_messages sigue produciendo
# system message correcto
# ════════════════════════════════════════════════════════════════════

def test_prepare_messages_system_message_matches_resolved() -> None:
    """Regresión del refactor: _prepare_messages usa internamente
    get_resolved_role_setup. El system message del run real es idéntico
    al output del método público."""
    agent = _mk_agent(role_setup="Sos preciso.", with_global_instructions=True)
    messages = agent._prepare_messages(
        "user prompt aquí",
        shelf_context="memoria activa adicional",
    )
    system_msg = messages[0]
    assert system_msg["role"] == "system"
    assert system_msg["content"] == agent.get_resolved_role_setup(
        shelf_context="memoria activa adicional"
    )


def test_user_message_unchanged_after_refactor() -> None:
    """Regresión: el user message es exactamente el prompt pasado."""
    agent = _mk_agent()
    messages = agent._prepare_messages("hola mundo")
    user_msg = messages[1]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "hola mundo"


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("get_schemas_output_is_json_serializable",
         test_get_schemas_output_is_json_serializable),
        ("get_resolved_role_setup_is_plain_string",
         test_get_resolved_role_setup_is_plain_string),
        ("agent_snapshot_persists_in_history_entry",
         test_agent_snapshot_persists_in_history_entry),
        ("current_run_config_returns_agent_snapshot",
         test_current_run_config_returns_agent_snapshot),
        ("prepare_messages_system_message_matches_resolved",
         test_prepare_messages_system_message_matches_resolved),
        ("user_message_unchanged_after_refactor",
         test_user_message_unchanged_after_refactor),
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
