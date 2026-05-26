"""
Tests del nuevo método ``RunParams.to_dict()`` (PR 4).

Doc rector: docs/design/runinfo-to-entries.md, "Fix necesario en core.py:
RunInfo.run_params debe capturar TODOS los kwargs" (líneas 387-413).

Dual-mode: script + pytest-compatible.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.core import RunParams, InstantNeoParams


# ════════════════════════════════════════════════════════════════════
# Estructura del snapshot
# ════════════════════════════════════════════════════════════════════

def test_to_dict_includes_basic_fields() -> None:
    """El snapshot incluye los campos básicos de BaseParams."""
    rp = RunParams(prompt="x", model="m", temperature=0.5, max_tokens=100)
    d = rp.to_dict()
    assert d["model"] == "m"
    assert d["temperature"] == 0.5
    assert d["max_tokens"] == 100


def test_to_dict_excludes_prompt() -> None:
    """``prompt`` NO aparece en el snapshot — vive en RunInfo.prompt aparte."""
    rp = RunParams(prompt="hola mundo", model="m")
    d = rp.to_dict()
    assert "prompt" not in d


def test_to_dict_excludes_additional_params_key() -> None:
    """``additional_params`` NO aparece como key nested — se hace spread al top level."""
    rp = RunParams(prompt="x", model="m")
    rp.additional_params["any_kwarg"] = "value"
    d = rp.to_dict()
    assert "additional_params" not in d
    assert d.get("any_kwarg") == "value"  # debe estar spreadeado


def test_to_dict_includes_role_setup_when_set() -> None:
    rp = RunParams(prompt="x", model="m", role_setup="Eres un experto")
    d = rp.to_dict()
    assert d["role_setup"] == "Eres un experto"


def test_to_dict_includes_image_detail() -> None:
    """``image_detail`` (kwarg per-run nuevo del v2) sí entra al snapshot."""
    rp = RunParams(prompt="x", model="m", image_detail="high")
    d = rp.to_dict()
    assert d["image_detail"] == "high"


def test_to_dict_spreads_additional_params() -> None:
    """Los kwargs custom (que van a additional_params) aparecen al top."""
    rp = RunParams(prompt="x", model="m")
    rp.additional_params["reasoning"] = "high"
    rp.additional_params["custom_flag"] = True
    rp.additional_params["nested_dict"] = {"a": 1}
    d = rp.to_dict()
    assert d["reasoning"] == "high"
    assert d["custom_flag"] is True
    assert d["nested_dict"] == {"a": 1}


def test_to_dict_preserves_none_values() -> None:
    """Campos en None se preservan (no se omiten). Útil para distinguir
    'no se pasó' de 'se pasó None' a futuro."""
    rp = RunParams(prompt="x", model="m")  # temperature default None
    d = rp.to_dict()
    assert "temperature" in d
    assert d["temperature"] is None


def test_to_dict_from_instantneo_params_full_snapshot() -> None:
    """Construir vía from_instantneo_params con kwargs custom: snapshot completo."""
    ip = InstantNeoParams(
        provider="openai", api_key="sk-test", role_setup="x", model="gpt-4",
        temperature=0.7, max_tokens=500,
    )
    rp = RunParams.from_instantneo_params(
        ip, prompt="qué tal", reasoning="high", image_detail="low",
        my_custom="value",
    )
    d = rp.to_dict()
    # Originales del InstantNeoParams
    assert d["model"] == "gpt-4"
    assert d["temperature"] == 0.7
    assert d["max_tokens"] == 500
    # Per-run overrides via kwargs
    assert d["image_detail"] == "low"
    # Spread de additional_params
    assert d["reasoning"] == "high"
    assert d["my_custom"] == "value"
    # Prompt excluido
    assert "prompt" not in d


def test_to_dict_returns_new_dict_each_call() -> None:
    """Cada llamada produce un dict nuevo (no compartido)."""
    rp = RunParams(prompt="x", model="m")
    d1 = rp.to_dict()
    d2 = rp.to_dict()
    d1["mutated"] = "X"
    assert "mutated" not in d2


def test_to_dict_additional_params_overrides_take_precedence_over_field_with_same_name() -> None:
    """Si por error un additional_param tiene el mismo nombre que un field,
    el spread lo sobreescribe en el snapshot. Documenta el comportamiento.

    En la práctica esto no debería pasar (from_instantneo_params usa setattr
    para campos reales y solo manda a additional_params lo que no es campo),
    pero captura el comportamiento si ocurre via manipulación directa."""
    rp = RunParams(prompt="x", model="original")
    rp.additional_params["model"] = "from_additional"
    d = rp.to_dict()
    assert d["model"] == "from_additional"


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("to_dict_includes_basic_fields",       test_to_dict_includes_basic_fields),
        ("to_dict_excludes_prompt",             test_to_dict_excludes_prompt),
        ("to_dict_excludes_additional_params_key", test_to_dict_excludes_additional_params_key),
        ("to_dict_includes_role_setup_when_set", test_to_dict_includes_role_setup_when_set),
        ("to_dict_includes_image_detail",       test_to_dict_includes_image_detail),
        ("to_dict_spreads_additional_params",   test_to_dict_spreads_additional_params),
        ("to_dict_preserves_none_values",       test_to_dict_preserves_none_values),
        ("to_dict_from_instantneo_params_full_snapshot", test_to_dict_from_instantneo_params_full_snapshot),
        ("to_dict_returns_new_dict_each_call",  test_to_dict_returns_new_dict_each_call),
        ("to_dict_additional_params_overrides_take_precedence_over_field_with_same_name",
         test_to_dict_additional_params_overrides_take_precedence_over_field_with_same_name),
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
