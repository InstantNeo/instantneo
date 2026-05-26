"""
Tests de propagación de ``reasoning_tokens`` en adapters (PR 4).

Doc rector: docs/design/runinfo-to-entries.md, sección "Fix requerido en
InstantNeo: reasoning_tokens" (líneas 239-275). El doc describe los
sitios exactos y los formatos esperados por provider.

Cada test mockea el response del provider y verifica que el adapter
lo traduce a ``StandardUsage.reasoning_tokens``.

Dual-mode: script + pytest-compatible.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.adapters.openai_adapter import OpenAIAdapter
from instantneo.adapters.cerebras_adapter import CerebrasAdapter
from instantneo.adapters.gemini_adapter import GeminiAdapter
from instantneo.adapters.anthropic_adapter import AnthropicAdapter


# ════════════════════════════════════════════════════════════════════
# OpenAI adapter
# ════════════════════════════════════════════════════════════════════

def _openai_response_mock(reasoning_tokens_source: str = None, reasoning_value: int = None):
    """Construye un mock de OpenAI response con o sin reasoning_tokens.

    reasoning_tokens_source: 'completion' | 'output' | None.
    """
    usage = SimpleNamespace(
        prompt_tokens=10, completion_tokens=20, total_tokens=30,
    )
    if reasoning_tokens_source == "completion":
        usage.completion_tokens_details = SimpleNamespace(reasoning_tokens=reasoning_value)
    elif reasoning_tokens_source == "output":
        usage.output_tokens_details = SimpleNamespace(reasoning_tokens=reasoning_value)

    # Mock de output: lista vacía (sin items relevantes) — usa output_text directo.
    response = SimpleNamespace(
        id="resp_abc",
        model="gpt-4o-mini",
        status="completed",
        usage=usage,
        output=[],
        output_text="hola",
    )
    return response


def test_openai_translates_reasoning_tokens_from_completion_details() -> None:
    """Chat Completions naming: completion_tokens_details.reasoning_tokens."""
    adapter = OpenAIAdapter(api_key="sk-test-dummy")
    response = _openai_response_mock("completion", 123)
    standard = adapter._translate_response(response)
    assert standard.usage.reasoning_tokens == 123


def test_openai_translates_reasoning_tokens_from_output_details() -> None:
    """Responses API naming: output_tokens_details.reasoning_tokens."""
    adapter = OpenAIAdapter(api_key="sk-test-dummy")
    response = _openai_response_mock("output", 99)
    standard = adapter._translate_response(response)
    assert standard.usage.reasoning_tokens == 99


def test_openai_no_reasoning_tokens_yields_none() -> None:
    """Sin esos campos en la response, reasoning_tokens queda None."""
    adapter = OpenAIAdapter(api_key="sk-test-dummy")
    response = _openai_response_mock(None)
    standard = adapter._translate_response(response)
    assert standard.usage.reasoning_tokens is None
    # Y el resto sigue OK (regresión)
    assert standard.usage.input_tokens == 10
    assert standard.usage.output_tokens == 20
    assert standard.usage.total_tokens == 30


# ════════════════════════════════════════════════════════════════════
# Cerebras adapter
# ════════════════════════════════════════════════════════════════════

def _cerebras_response_mock(reasoning_value: int = None, with_choice: bool = True):
    """Mock de Cerebras response."""
    usage = SimpleNamespace(
        prompt_tokens=15, completion_tokens=25, total_tokens=40,
    )
    if reasoning_value is not None:
        usage.completion_tokens_details = SimpleNamespace(reasoning_tokens=reasoning_value)

    if with_choice:
        choice = SimpleNamespace(
            index=0,
            message=SimpleNamespace(content="ok", tool_calls=None, reasoning=None),
            finish_reason="stop",
        )
        choices = [choice]
    else:
        choices = []

    return SimpleNamespace(
        id="cb_xyz", model="qwen-3", usage=usage, choices=choices,
    )


def test_cerebras_translates_reasoning_tokens() -> None:
    adapter = CerebrasAdapter(api_key="csk-test-dummy")
    response = _cerebras_response_mock(reasoning_value=77)
    standard = adapter._translate_response(response)
    assert standard.usage.reasoning_tokens == 77


def test_cerebras_no_reasoning_tokens_yields_none() -> None:
    adapter = CerebrasAdapter(api_key="csk-test-dummy")
    response = _cerebras_response_mock(reasoning_value=None)
    standard = adapter._translate_response(response)
    assert standard.usage.reasoning_tokens is None


def test_cerebras_error_path_also_propagates_reasoning_tokens() -> None:
    """El path de error (sin choice) también construye StandardUsage —
    debe incluir reasoning_tokens (default None aquí)."""
    adapter = CerebrasAdapter(api_key="csk-test-dummy")
    response = _cerebras_response_mock(reasoning_value=None, with_choice=False)
    standard = adapter._translate_response(response)
    assert standard.usage.reasoning_tokens is None
    # input/output siguen presentes
    assert standard.usage.input_tokens == 15


# ════════════════════════════════════════════════════════════════════
# Gemini adapter
# ════════════════════════════════════════════════════════════════════

def _gemini_response_mock(thoughts_count: int = None, with_candidate: bool = True):
    """Mock de Gemini response."""
    usage_metadata = SimpleNamespace(
        prompt_token_count=30,
        candidates_token_count=40,
        total_token_count=70,
    )
    if thoughts_count is not None:
        usage_metadata.thoughts_token_count = thoughts_count

    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[SimpleNamespace(text="hola", function_call=None)]),
        finish_reason="STOP",
    ) if with_candidate else None

    return SimpleNamespace(
        candidates=[candidate] if candidate else [],
        usage_metadata=usage_metadata,
        model_version="gemini-2.5-flash",
    )


def test_gemini_translates_thoughts_token_count() -> None:
    """Gemini 2.5+ expone thoughts_token_count en usage_metadata."""
    adapter = GeminiAdapter(api_key="gem-test-dummy")
    response = _gemini_response_mock(thoughts_count=55)
    standard = adapter._translate_response(response, model="gemini-2.5-flash")
    assert standard.usage.reasoning_tokens == 55


def test_gemini_no_thoughts_yields_none() -> None:
    """Sin thoughts_token_count (modelo viejo, p.ej. Gemini 1.5), None."""
    adapter = GeminiAdapter(api_key="gem-test-dummy")
    response = _gemini_response_mock(thoughts_count=None)
    standard = adapter._translate_response(response, model="gemini-1.5-pro")
    assert standard.usage.reasoning_tokens is None


# ════════════════════════════════════════════════════════════════════
# Anthropic adapter — no aplica
# ════════════════════════════════════════════════════════════════════

def test_anthropic_yields_none_by_design() -> None:
    """Anthropic cuenta thinking tokens dentro de output_tokens, sin
    campo separado. StandardUsage.reasoning_tokens queda None por default
    — exactamente lo correcto. NO se tocó el adapter en este PR."""
    adapter = AnthropicAdapter(api_key="sk-ant-test-dummy")
    response = SimpleNamespace(
        id="msg_001",
        model="claude-haiku-4-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=15),
        content=[SimpleNamespace(type="text", text="hola")],
        stop_reason="end_turn",
    )
    standard = adapter._translate_response(response)
    assert standard.usage.reasoning_tokens is None
    # input/output preservados (regresión)
    assert standard.usage.input_tokens == 10
    assert standard.usage.output_tokens == 15
    assert standard.usage.total_tokens == 25


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("openai_translates_reasoning_tokens_from_completion_details",
         test_openai_translates_reasoning_tokens_from_completion_details),
        ("openai_translates_reasoning_tokens_from_output_details",
         test_openai_translates_reasoning_tokens_from_output_details),
        ("openai_no_reasoning_tokens_yields_none",
         test_openai_no_reasoning_tokens_yields_none),
        ("cerebras_translates_reasoning_tokens",
         test_cerebras_translates_reasoning_tokens),
        ("cerebras_no_reasoning_tokens_yields_none",
         test_cerebras_no_reasoning_tokens_yields_none),
        ("cerebras_error_path_also_propagates_reasoning_tokens",
         test_cerebras_error_path_also_propagates_reasoning_tokens),
        ("gemini_translates_thoughts_token_count",
         test_gemini_translates_thoughts_token_count),
        ("gemini_no_thoughts_yields_none",
         test_gemini_no_thoughts_yields_none),
        ("anthropic_yields_none_by_design",
         test_anthropic_yields_none_by_design),
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
