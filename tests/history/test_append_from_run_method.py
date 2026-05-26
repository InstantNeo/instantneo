"""
Tests del método de conveniencia ``History.append_from_run`` (PR 5).

Verifica que el wrapper delega correctamente al ``append_entry_from_run``
de ``instantneo.history.from_run_info`` y que el lazy import no causa
ciclos.

Dual-mode.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.history.from_run_info import append_entry_from_run


def _mk_simple_run_info():
    return SimpleNamespace(
        error=None,
        response_content="hi",
        reasoning=None,
        finish_reason="stop",
        usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8, "reasoning_tokens": None},
        duration_ms=10.0,
        provider="openai",
        model="m",
        timestamp="2026-05-11T00:00:00Z",
        run_params={"model": "m"},
        provider_timing=None,
        llm_calls=[SimpleNamespace(response_id="r", response_model="m")],
        tool_executions=[],
    )


def test_history_append_from_run_delegates_to_function() -> None:
    """history.append_from_run(...) y append_entry_from_run(history, ...)
    producen entries equivalentes."""
    h1 = History()
    h2 = History()
    ri = _mk_simple_run_info()

    via_method = h1.append_from_run(ri, turn_num=1, author="A",
                                     origin="o", run_id="r")
    via_function = append_entry_from_run(h2, ri, turn_num=1, author="A",
                                          origin="o", run_id="r")

    # Mismo número de entries
    assert len(via_method) == len(via_function)
    # Mismo shape de content (excepto timestamp que difiere por momento de escritura)
    for em, ef in zip(via_method, via_function):
        assert em.type == ef.type
        assert em.author == ef.author
        assert em.content == ef.content


def test_history_append_from_run_returns_appended_entries() -> None:
    """El return value coincide con lo que termina en history.all()."""
    h = History()
    ri = _mk_simple_run_info()
    ret = h.append_from_run(ri, turn_num=2, author="A", origin="o", run_id="r")
    assert ret == h.all()


def test_history_append_from_run_works_multiple_times() -> None:
    """Llamar al método varias veces acumula entries correctamente."""
    h = History()
    ri = _mk_simple_run_info()
    h.append_from_run(ri, turn_num=1, author="A", origin="o", run_id="r1")
    h.append_from_run(ri, turn_num=2, author="A", origin="o", run_id="r2")
    h.append_from_run(ri, turn_num=3, author="A", origin="o", run_id="r3")
    assert len(h.all()) == 3
    # Ids consecutivos
    assert [e.id for e in h.all()] == [1, 2, 3]
    # turn_num distintos preservados
    assert [e.content["turn_num"] for e in h.all()] == [1, 2, 3]


def test_history_append_from_run_lazy_import_does_not_cycle() -> None:
    """El lazy import dentro del método no debe causar ImportError
    ni recursión infinita cuando se invoca varias veces."""
    h = History()
    ri = _mk_simple_run_info()
    # Múltiples invocaciones — si hay ciclo, falla acá
    for i in range(5):
        h.append_from_run(ri, turn_num=i, author="A", origin="o", run_id="r")
    assert len(h.all()) == 5


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("history_append_from_run_delegates_to_function",
         test_history_append_from_run_delegates_to_function),
        ("history_append_from_run_returns_appended_entries",
         test_history_append_from_run_returns_appended_entries),
        ("history_append_from_run_works_multiple_times",
         test_history_append_from_run_works_multiple_times),
        ("history_append_from_run_lazy_import_does_not_cycle",
         test_history_append_from_run_lazy_import_does_not_cycle),
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
