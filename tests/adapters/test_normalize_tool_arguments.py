"""
Tests del fix en ``_chat_completions._normalize_tool_arguments``.

Bug original (descubierto durante smoke real del PR 5 contra Groq):
algunos providers chat-completions devuelven ``arguments: "null"`` o
cadena vacía cuando la tool no requiere args. Eso producía
``json.loads("null") = None`` y luego ``tool_func(**None) → TypeError``.

El fix normaliza al borde del adapter: ``None`` / ``""`` / ``"null"``
→ ``"{}"``. Args reales pasan intactos.

Dual-mode.
"""
import sys
import json
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.adapters._chat_completions import (
    _normalize_tool_arguments, ChatCompletionsAdapter,
)
from instantneo.adapters.groq_adapter import GroqAdapter


# ════════════════════════════════════════════════════════════════════
# _normalize_tool_arguments — unit puro
# ════════════════════════════════════════════════════════════════════

def test_normalize_none_to_empty_dict_string() -> None:
    assert _normalize_tool_arguments(None) == "{}"


def test_normalize_empty_string_to_empty_dict_string() -> None:
    assert _normalize_tool_arguments("") == "{}"


def test_normalize_whitespace_string_to_empty_dict_string() -> None:
    assert _normalize_tool_arguments("   ") == "{}"


def test_normalize_literal_null_to_empty_dict_string() -> None:
    """Caso clave: Groq devuelve esto cuando la tool no requiere args."""
    assert _normalize_tool_arguments("null") == "{}"


def test_normalize_literal_null_with_whitespace() -> None:
    assert _normalize_tool_arguments("  null  ") == "{}"


def test_normalize_passes_real_args_intact() -> None:
    """Args reales (JSON-string de un dict) pasan tal cual, sin cambio."""
    payload = '{"key": "value", "n": 42}'
    assert _normalize_tool_arguments(payload) == payload


def test_normalize_passes_empty_dict_string_intact() -> None:
    """``"{}"`` ya está normalizado, pasa intacto."""
    assert _normalize_tool_arguments("{}") == "{}"


def test_normalize_output_is_always_json_loadable_to_dict() -> None:
    """Garantía contract: el output siempre json.loads-eable a dict."""
    for raw in [None, "", "null", "  ", '{"a": 1}', "{}"]:
        normalized = _normalize_tool_arguments(raw)
        loaded = json.loads(normalized)
        assert isinstance(loaded, dict), f"raw={raw!r} normalized={normalized!r} loaded={loaded!r}"


# ════════════════════════════════════════════════════════════════════
# Integración: _translate_response del adapter aplica la normalización
# ════════════════════════════════════════════════════════════════════

def _mk_chat_completion_response(tool_call_arguments) -> SimpleNamespace:
    """Mock de ChatCompletionResponse con un tool_call cuyo `arguments`
    es el valor dado."""
    function = SimpleNamespace(name="my_tool", arguments=tool_call_arguments)
    tc = SimpleNamespace(id="tc_001", function=function)
    # message necesita `reasoning` para satisfacer `_translate_response`
    # del ChatCompletionsAdapter (Groq etc) que lo lee defensivo.
    message = SimpleNamespace(content=None, tool_calls=[tc], reasoning=None)
    choice = SimpleNamespace(message=message, finish_reason="tool_calls", index=0)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15,
                            reasoning_tokens=None)
    return SimpleNamespace(id="resp_001", model="llama-3.3", choices=[choice], usage=usage)


def test_adapter_translates_null_arguments_to_empty_dict_string() -> None:
    """Confirma que pasando una response con arguments='null' produce
    StandardToolCall.arguments == '{}'."""
    adapter = GroqAdapter(api_key="gsk-test")
    response = _mk_chat_completion_response("null")
    standard = adapter._translate_response(response)

    tcs = standard.choices[0].message.tool_calls
    assert tcs is not None
    assert len(tcs) == 1
    assert tcs[0].arguments == "{}"


def test_adapter_translates_none_arguments_to_empty_dict_string() -> None:
    adapter = GroqAdapter(api_key="gsk-test")
    response = _mk_chat_completion_response(None)
    standard = adapter._translate_response(response)
    assert standard.choices[0].message.tool_calls[0].arguments == "{}"


def test_adapter_preserves_real_arguments() -> None:
    adapter = GroqAdapter(api_key="gsk-test")
    payload = '{"query": "x", "limit": 5}'
    response = _mk_chat_completion_response(payload)
    standard = adapter._translate_response(response)
    assert standard.choices[0].message.tool_calls[0].arguments == payload


# ════════════════════════════════════════════════════════════════════
# Cinturón de seguridad en core: json.loads(...) or {}
# ════════════════════════════════════════════════════════════════════

def test_core_or_pattern_handles_json_loads_returning_none() -> None:
    """Documenta el cinturón de seguridad de core.py:820.

    json.loads('null') → None; `None or {}` → `{}`. Evita TypeError
    en tool_func(**None) si por cualquier ruta el adapter dejara pasar
    'null'."""
    raw = "null"
    result = json.loads(raw) or {}
    assert result == {}


def test_core_or_pattern_does_not_alter_real_args() -> None:
    raw = '{"k": "v"}'
    result = json.loads(raw) or {}
    assert result == {"k": "v"}


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("normalize_none_to_empty_dict_string",        test_normalize_none_to_empty_dict_string),
        ("normalize_empty_string_to_empty_dict_string", test_normalize_empty_string_to_empty_dict_string),
        ("normalize_whitespace_string_to_empty_dict_string", test_normalize_whitespace_string_to_empty_dict_string),
        ("normalize_literal_null_to_empty_dict_string", test_normalize_literal_null_to_empty_dict_string),
        ("normalize_literal_null_with_whitespace",     test_normalize_literal_null_with_whitespace),
        ("normalize_passes_real_args_intact",          test_normalize_passes_real_args_intact),
        ("normalize_passes_empty_dict_string_intact",  test_normalize_passes_empty_dict_string_intact),
        ("normalize_output_is_always_json_loadable_to_dict", test_normalize_output_is_always_json_loadable_to_dict),
        ("adapter_translates_null_arguments_to_empty_dict_string", test_adapter_translates_null_arguments_to_empty_dict_string),
        ("adapter_translates_none_arguments_to_empty_dict_string", test_adapter_translates_none_arguments_to_empty_dict_string),
        ("adapter_preserves_real_arguments",           test_adapter_preserves_real_arguments),
        ("core_or_pattern_handles_json_loads_returning_none", test_core_or_pattern_handles_json_loads_returning_none),
        ("core_or_pattern_does_not_alter_real_args",   test_core_or_pattern_does_not_alter_real_args),
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
