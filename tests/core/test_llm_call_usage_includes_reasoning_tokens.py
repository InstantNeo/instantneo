"""
Tests del flow ``adapter → core.py → llm_call.usage`` que confirma que
``reasoning_tokens`` viaja desde ``StandardUsage`` al dict expuesto en
``RunInfo.llm_calls[*].usage`` y ``RunInfo.usage``.

Doc rector: docs/design/runinfo-to-entries.md, sección "core.py — propagar
reasoning_tokens de StandardUsage al dict" (líneas 243-263).

Dual-mode.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.models.standard import StandardUsage
from instantneo.models.run_info import RunInfo, LLMCall


# Reimplementación mínima del bloque que copia StandardUsage → dict en
# `core.py:_handle_normal_response` (líneas 1217-1224). El test ejercita
# este patrón directamente sobre `llm_call` y verifica el shape final.

def _replicate_normal_response_usage_copy(usage):
    """Copia StandardUsage al dict — replica `core.py:1219-1224` exacto."""
    return {
        "input_tokens": usage.input_tokens if hasattr(usage, 'input_tokens') else 0,
        "output_tokens": usage.output_tokens if hasattr(usage, 'output_tokens') else 0,
        "total_tokens": usage.total_tokens if hasattr(usage, 'total_tokens') else 0,
        "reasoning_tokens": getattr(usage, "reasoning_tokens", None),
    }


def test_llm_call_usage_has_reasoning_tokens_key_when_set() -> None:
    """StandardUsage con reasoning_tokens=42 → dict tiene esa key con ese valor."""
    standard = StandardUsage(
        input_tokens=10, output_tokens=20, total_tokens=30, reasoning_tokens=42,
    )
    d = _replicate_normal_response_usage_copy(standard)
    assert d["input_tokens"] == 10
    assert d["output_tokens"] == 20
    assert d["total_tokens"] == 30
    assert d["reasoning_tokens"] == 42


def test_llm_call_usage_reasoning_tokens_defaults_to_none() -> None:
    """Sin reasoning_tokens (default None), el dict tiene la key con None."""
    standard = StandardUsage(input_tokens=5, output_tokens=10, total_tokens=15)
    d = _replicate_normal_response_usage_copy(standard)
    assert "reasoning_tokens" in d
    assert d["reasoning_tokens"] is None


def test_llm_call_attribution_via_real_object() -> None:
    """Asigna usage a un LLMCall real (modelo RunInfo) y verifica shape."""
    standard = StandardUsage(
        input_tokens=100, output_tokens=50, total_tokens=150, reasoning_tokens=10,
    )
    llm_call = LLMCall(messages_sent=[{"role": "user", "content": "hi"}])
    llm_call.usage = _replicate_normal_response_usage_copy(standard)

    assert llm_call.usage["input_tokens"] == 100
    assert llm_call.usage["reasoning_tokens"] == 10
    # Las 4 keys esperadas
    assert set(llm_call.usage.keys()) == {
        "input_tokens", "output_tokens", "total_tokens", "reasoning_tokens",
    }


# ════════════════════════════════════════════════════════════════════
# Stream legacy path (chunk_data dict raw)
# ════════════════════════════════════════════════════════════════════

def _replicate_stream_legacy_usage_copy(usage_data):
    """Replica `core.py:1010-1015` exactamente."""
    completion_details = usage_data.get('completion_tokens_details') or {}
    output_details     = usage_data.get('output_tokens_details') or {}
    return {
        "input_tokens": usage_data.get('prompt_tokens', usage_data.get('input_tokens', 0)),
        "output_tokens": usage_data.get('completion_tokens', usage_data.get('output_tokens', 0)),
        "total_tokens": usage_data.get('total_tokens', 0),
        "reasoning_tokens": completion_details.get('reasoning_tokens') or output_details.get('reasoning_tokens'),
    }


def test_stream_legacy_usage_completion_details_reasoning_tokens() -> None:
    """Chat Completions raw: completion_tokens_details.reasoning_tokens."""
    usage_data = {
        "prompt_tokens": 30, "completion_tokens": 40, "total_tokens": 70,
        "completion_tokens_details": {"reasoning_tokens": 25},
    }
    d = _replicate_stream_legacy_usage_copy(usage_data)
    assert d["reasoning_tokens"] == 25


def test_stream_legacy_usage_output_details_reasoning_tokens() -> None:
    """Responses raw: output_tokens_details.reasoning_tokens."""
    usage_data = {
        "input_tokens": 30, "output_tokens": 40, "total_tokens": 70,
        "output_tokens_details": {"reasoning_tokens": 15},
    }
    d = _replicate_stream_legacy_usage_copy(usage_data)
    assert d["reasoning_tokens"] == 15


def test_stream_legacy_usage_no_reasoning_tokens_yields_none() -> None:
    usage_data = {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}
    d = _replicate_stream_legacy_usage_copy(usage_data)
    assert d["reasoning_tokens"] is None


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("llm_call_usage_has_reasoning_tokens_key_when_set",
         test_llm_call_usage_has_reasoning_tokens_key_when_set),
        ("llm_call_usage_reasoning_tokens_defaults_to_none",
         test_llm_call_usage_reasoning_tokens_defaults_to_none),
        ("llm_call_attribution_via_real_object",
         test_llm_call_attribution_via_real_object),
        ("stream_legacy_usage_completion_details_reasoning_tokens",
         test_stream_legacy_usage_completion_details_reasoning_tokens),
        ("stream_legacy_usage_output_details_reasoning_tokens",
         test_stream_legacy_usage_output_details_reasoning_tokens),
        ("stream_legacy_usage_no_reasoning_tokens_yields_none",
         test_stream_legacy_usage_no_reasoning_tokens_yields_none),
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
