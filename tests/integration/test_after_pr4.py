"""
Tests transversales después del PR 4 (cross PR 2 + PR 4).

Verifican que el snapshot completo de ``run_params`` y el ``reasoning_tokens``
ahora propagado pueden guardarse correctamente en un History (PR 2) y
sobrevivir el roundtrip JSON.

Dual-mode. No requieren red ni LLM.
"""
import sys
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.core import RunParams
from instantneo.history import History


def test_run_params_snapshot_with_custom_kwargs_in_history_entry() -> None:
    """Caso de uso real: el bridge (futuro PR 5) va a tomar
    ``run_params.to_dict()`` y meterlo en ``content["run_params"]`` de
    una entry tipo response. Verificar que el snapshot completo (con
    reasoning, image_detail, custom kwargs) sobrevive el roundtrip JSON."""
    rp = RunParams(prompt="qué tal", model="o4-mini", temperature=0.7, image_detail="high")
    rp.additional_params["reasoning"] = "high"
    rp.additional_params["my_custom"] = {"nested": [1, 2, 3]}
    snapshot = rp.to_dict()

    # Simular lo que hará el bridge
    h = History()
    h.append(
        author="bridge_simulated",
        type="response",
        content={
            "text": "hola, ¿en qué te ayudo?",
            "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                      "reasoning_tokens": 25},
            "run_params": snapshot,
        },
    )

    # Roundtrip
    js = h.to_json()
    h2 = History.from_dicts(json.loads(js))

    restored = h2.all()[0]
    restored_snapshot = restored.content["run_params"]

    # Los kwargs custom sobrevivieron
    assert restored_snapshot["reasoning"] == "high"
    assert restored_snapshot["image_detail"] == "high"
    assert restored_snapshot["my_custom"] == {"nested": [1, 2, 3]}
    # Los fields normales también
    assert restored_snapshot["model"] == "o4-mini"
    assert restored_snapshot["temperature"] == 0.7
    # Prompt NO está duplicado (vive en RunInfo.prompt aparte)
    assert "prompt" not in restored_snapshot
    # reasoning_tokens del usage también
    assert restored.content["usage"]["reasoning_tokens"] == 25


def test_reasoning_tokens_in_usage_passes_through_to_history_entry() -> None:
    """Usage dict con reasoning_tokens va al History y sobrevive roundtrip."""
    h = History()
    h.append(
        author="bridge_simulated",
        type="response",
        content={
            "text": "...",
            "usage": {
                "input_tokens": 200, "output_tokens": 80, "total_tokens": 280,
                "reasoning_tokens": 50,
            },
        },
    )
    h2 = History.from_dicts(json.loads(h.to_json()))
    usage = h2.all()[0].content["usage"]
    assert usage["reasoning_tokens"] == 50
    assert usage["total_tokens"] == 280


def test_usage_with_reasoning_tokens_none_roundtrips() -> None:
    """reasoning_tokens=None es JSON-safe y sobrevive roundtrip."""
    h = History()
    h.append(
        author="bridge", type="response",
        content={"usage": {"input_tokens": 5, "output_tokens": 10,
                           "total_tokens": 15, "reasoning_tokens": None}},
    )
    h2 = History.from_dicts(json.loads(h.to_json()))
    usage = h2.all()[0].content["usage"]
    assert usage["reasoning_tokens"] is None


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("run_params_snapshot_with_custom_kwargs_in_history_entry",
         test_run_params_snapshot_with_custom_kwargs_in_history_entry),
        ("reasoning_tokens_in_usage_passes_through_to_history_entry",
         test_reasoning_tokens_in_usage_passes_through_to_history_entry),
        ("usage_with_reasoning_tokens_none_roundtrips",
         test_usage_with_reasoning_tokens_none_roundtrips),
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
