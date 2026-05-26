"""
Tests de ``AgentCapabilities.get_schemas`` (PR 6).

Doc rector: docs/design/log-design.md líneas 1273-1274 (Pre-requisito 2).
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo import AgentCapabilities, tool


# ────────────────────────────────────────────────────────────────────
# Fixtures: tools de prueba
# ────────────────────────────────────────────────────────────────────

@tool(description="Get current weather", parameters={
    "location": {"description": "City name", "type": "str"},
})
def get_weather(location: str) -> dict:
    return {"location": location, "temp": 22}


@tool(description="Add two integers", parameters={
    "a": {"description": "First", "type": "int"},
    "b": {"description": "Second", "type": "int"},
})
def add(a: int, b: int) -> int:
    return a + b


@tool(description="Returns true if value is in allowed list", parameters={
    "value": {"description": "Value", "type": "str",
              "enum": ["red", "green", "blue"]},
})
def check_color(value: str) -> bool:
    return value in ("red", "green", "blue")


# ════════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════════

def test_empty_capabilities_returns_empty_list() -> None:
    caps = AgentCapabilities()
    assert caps.get_schemas() == []


def test_single_tool_returns_one_schema() -> None:
    caps = AgentCapabilities(skills=[get_weather])
    schemas = caps.get_schemas()
    assert len(schemas) == 1


def test_multi_tool_returns_n_schemas() -> None:
    caps = AgentCapabilities(skills=[get_weather, add, check_color])
    schemas = caps.get_schemas()
    assert len(schemas) == 3
    names = sorted(s["function"]["name"] for s in schemas)
    assert names == ["add", "check_color", "get_weather"]


def test_schema_shape_openai_format() -> None:
    """Cada schema sigue el formato OpenAI: type=function + function dict."""
    caps = AgentCapabilities(skills=[get_weather])
    s = caps.get_schemas()[0]
    assert s["type"] == "function"
    assert "function" in s
    fn = s["function"]
    assert fn["name"] == "get_weather"
    assert fn["description"] == "Get current weather"
    assert fn["parameters"]["type"] == "object"
    assert "location" in fn["parameters"]["properties"]
    assert fn["parameters"]["properties"]["location"]["type"] == "string"


def test_schema_preserves_required() -> None:
    """Los parametros requeridos aparecen en `required` list."""
    caps = AgentCapabilities(skills=[add])
    s = caps.get_schemas()[0]
    required = s["function"]["parameters"]["required"]
    # add(a, b) — ambos requeridos (no tienen default)
    assert sorted(required) == ["a", "b"]


def test_schema_preserves_enum() -> None:
    """Si un parámetro tiene `enum`, el schema lo preserva."""
    caps = AgentCapabilities(skills=[check_color])
    s = caps.get_schemas()[0]
    enum = s["function"]["parameters"]["properties"]["value"].get("enum")
    assert enum == ["red", "green", "blue"]


def test_get_schemas_is_idempotent() -> None:
    """Llamar get_schemas() varias veces produce el mismo resultado."""
    caps = AgentCapabilities(skills=[get_weather, add])
    s1 = caps.get_schemas()
    s2 = caps.get_schemas()
    assert s1 == s2
    # No comparten referencias mutables (cada llamada produce listas nuevas)
    assert s1 is not s2


def test_get_schemas_via_agent_capabilities_attribute() -> None:
    """``agent.capabilities.get_schemas()`` funciona — patrón documentado
    en docs/design/log-design.md:1273."""
    from instantneo import InstantNeo
    caps = AgentCapabilities(skills=[get_weather])
    agent = InstantNeo(
        provider="openai", model="gpt-5-mini", api_key="sk-test",
        role_setup="x", tools=caps,
    )
    schemas = agent.capabilities.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "get_weather"


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("empty_capabilities_returns_empty_list", test_empty_capabilities_returns_empty_list),
        ("single_tool_returns_one_schema",         test_single_tool_returns_one_schema),
        ("multi_tool_returns_n_schemas",           test_multi_tool_returns_n_schemas),
        ("schema_shape_openai_format",             test_schema_shape_openai_format),
        ("schema_preserves_required",              test_schema_preserves_required),
        ("schema_preserves_enum",                  test_schema_preserves_enum),
        ("get_schemas_is_idempotent",              test_get_schemas_is_idempotent),
        ("get_schemas_via_agent_capabilities_attribute", test_get_schemas_via_agent_capabilities_attribute),
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
