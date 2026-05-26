"""
Tests de helpers del módulo ``instantneo.debug``:
``sanitize_secrets``, ``write_json``, ``build_agent_config``,
``extract_tool_schemas``.

Dual-mode.
"""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo import InstantNeo, AgentCapabilities, tool
from instantneo.debug import (
    sanitize_secrets, write_json,
    build_agent_config, extract_tool_schemas,
)


# ════════════════════════════════════════════════════════════════════
# sanitize_secrets
# ════════════════════════════════════════════════════════════════════

def test_sanitize_explicit_keys() -> None:
    """api_key, service_account_file, location se filtran."""
    out = sanitize_secrets({
        "api_key": "sk-abc",
        "service_account_file": "creds.json",
        "location": "us-central1",
        "model": "gpt-5",
    })
    assert "api_key" not in out
    assert "service_account_file" not in out
    assert "location" not in out
    assert out["model"] == "gpt-5"


def test_sanitize_pattern_keys_case_insensitive() -> None:
    """Cualquier key con 'key'/'token'/'secret'/'password'/'credential' (CI)."""
    out = sanitize_secrets({
        "API_KEY": "x",
        "BearerToken": "y",
        "my_secret_thing": "z",
        "User_Password": "w",
        "AWS_CREDENTIALS": "c",
        "ok": "stays",
    })
    assert "API_KEY" not in out
    assert "BearerToken" not in out
    assert "my_secret_thing" not in out
    assert "User_Password" not in out
    assert "AWS_CREDENTIALS" not in out
    assert out == {"ok": "stays"}


def test_sanitize_recursive_on_nested_dicts() -> None:
    out = sanitize_secrets({
        "outer_ok": "1",
        "nested": {
            "api_key": "leaked",
            "model": "kept",
            "deeper": {"token": "leaked", "data": "kept"},
        },
    })
    assert "api_key" not in out["nested"]
    assert out["nested"]["model"] == "kept"
    assert "token" not in out["nested"]["deeper"]
    assert out["nested"]["deeper"]["data"] == "kept"


def test_sanitize_does_not_mutate_input() -> None:
    original = {"api_key": "secret", "model": "x"}
    sanitize_secrets(original)
    assert "api_key" in original  # original sigue intacto


def test_sanitize_non_dict_returned_as_is() -> None:
    assert sanitize_secrets("string") == "string"
    assert sanitize_secrets([1, 2, 3]) == [1, 2, 3]
    assert sanitize_secrets(None) is None


# ════════════════════════════════════════════════════════════════════
# write_json
# ════════════════════════════════════════════════════════════════════

def test_write_json_basic_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.json"
        data = {"a": 1, "b": "hola", "list": [1, 2, 3]}
        write_json(path, data)
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == data


def test_write_json_handles_non_json_safe_via_default_str() -> None:
    """datetime y otros tipos no estándar se serializan vía str()."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.json"
        data = {"when": datetime(2026, 5, 11, 12, 0, 0)}
        write_json(path, data)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert "2026-05-11" in loaded["when"]


def test_write_json_creates_parent_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "deep" / "nested" / "dir" / "f.json"
        write_json(path, {"ok": True})
        assert path.exists()


def test_write_json_preserves_utf8() -> None:
    """ensure_ascii=False → caracteres no-ASCII se preservan literales."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.json"
        write_json(path, {"texto": "hola, ñandú, café"})
        content = path.read_text(encoding="utf-8")
        assert "ñandú" in content
        assert "café" in content


# ════════════════════════════════════════════════════════════════════
# build_agent_config + extract_tool_schemas
# ════════════════════════════════════════════════════════════════════

@tool(description="Get weather", parameters={
    "city": {"description": "City", "type": "str"},
})
def get_weather(city: str) -> dict:
    return {"city": city}


def _mk_agent_with_secrets():
    """Construye un agente con api_key real para confirmar que se filtra."""
    return InstantNeo(
        provider="openai", model="gpt-5-mini",
        api_key="sk-test-LEAK_SHOULD_NOT_PERSIST",
        role_setup="Soy un agente.",
        temperature=0.7, max_tokens=200,
        tools=AgentCapabilities(skills=[get_weather]),
    )


def test_build_agent_config_shape() -> None:
    agent = _mk_agent_with_secrets()
    cfg = build_agent_config(agent)
    assert "name" in cfg
    assert cfg["provider"] == "openai"
    assert cfg["model"] == "gpt-5-mini"
    assert cfg["role_setup"] == "Soy un agente."
    assert isinstance(cfg["role_setup_resolved"], str)
    assert isinstance(cfg["tools"], list)
    assert isinstance(cfg["defaults"], dict)


def test_build_agent_config_includes_tools() -> None:
    agent = _mk_agent_with_secrets()
    cfg = build_agent_config(agent)
    assert len(cfg["tools"]) == 1
    assert cfg["tools"][0]["function"]["name"] == "get_weather"


def test_build_agent_config_does_not_leak_api_key() -> None:
    """REQUISITO CRÍTICO: api_key NO debe aparecer en el output."""
    agent = _mk_agent_with_secrets()
    cfg = build_agent_config(agent)
    serialized = json.dumps(cfg)
    assert "sk-test" not in serialized
    assert "LEAK_SHOULD_NOT_PERSIST" not in serialized


def test_build_agent_config_defaults_sanitized() -> None:
    """`defaults` viene sin secrets."""
    agent = _mk_agent_with_secrets()
    cfg = build_agent_config(agent)
    assert "api_key" not in cfg["defaults"]
    assert "service_account_file" not in cfg["defaults"]
    assert "location" not in cfg["defaults"]
    # Pero los campos no-secret SÍ están
    assert cfg["defaults"]["model"] == "gpt-5-mini"
    assert cfg["defaults"]["temperature"] == 0.7


def test_build_agent_config_name_defaults_to_agent_string() -> None:
    """Si el agente no tiene .name, defaultea a 'agent'."""
    agent = _mk_agent_with_secrets()
    cfg = build_agent_config(agent)
    assert cfg["name"] == "agent"


def test_extract_tool_schemas_equals_capabilities_get_schemas() -> None:
    """Wrapper devuelve lo mismo que `agent.capabilities.get_schemas()`."""
    agent = _mk_agent_with_secrets()
    assert extract_tool_schemas(agent) == agent.capabilities.get_schemas()


def test_extract_tool_schemas_empty_when_no_tools() -> None:
    agent = InstantNeo(
        provider="openai", model="gpt-5-mini", api_key="x",
        role_setup="x",
    )
    assert extract_tool_schemas(agent) == []


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("sanitize_explicit_keys",                 test_sanitize_explicit_keys),
        ("sanitize_pattern_keys_case_insensitive", test_sanitize_pattern_keys_case_insensitive),
        ("sanitize_recursive_on_nested_dicts",     test_sanitize_recursive_on_nested_dicts),
        ("sanitize_does_not_mutate_input",         test_sanitize_does_not_mutate_input),
        ("sanitize_non_dict_returned_as_is",       test_sanitize_non_dict_returned_as_is),
        ("write_json_basic_roundtrip",             test_write_json_basic_roundtrip),
        ("write_json_handles_non_json_safe_via_default_str", test_write_json_handles_non_json_safe_via_default_str),
        ("write_json_creates_parent_dirs",         test_write_json_creates_parent_dirs),
        ("write_json_preserves_utf8",              test_write_json_preserves_utf8),
        ("build_agent_config_shape",               test_build_agent_config_shape),
        ("build_agent_config_includes_tools",      test_build_agent_config_includes_tools),
        ("build_agent_config_does_not_leak_api_key", test_build_agent_config_does_not_leak_api_key),
        ("build_agent_config_defaults_sanitized",  test_build_agent_config_defaults_sanitized),
        ("build_agent_config_name_defaults_to_agent_string", test_build_agent_config_name_defaults_to_agent_string),
        ("extract_tool_schemas_equals_capabilities_get_schemas", test_extract_tool_schemas_equals_capabilities_get_schemas),
        ("extract_tool_schemas_empty_when_no_tools", test_extract_tool_schemas_empty_when_no_tools),
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
