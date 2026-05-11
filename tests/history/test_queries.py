"""
Tests de ``instantneo.history.queries``: ``current_origin`` y
``current_run_id`` (los dos helpers adelantados en PR 3; el resto
se agrega en PR 5).

Dual-mode.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.history.queries import current_origin, current_run_id


# ════════════════════════════════════════════════════════════════════
# current_origin
# ════════════════════════════════════════════════════════════════════

def test_current_origin_returns_none_on_empty_history() -> None:
    assert current_origin(History()) is None


def test_current_origin_returns_value_from_latest_entry_with_origin() -> None:
    h = History()
    h.append(author="u", type="t", content={"origin": "loop_alpha"})
    assert current_origin(h) == "loop_alpha"


def test_current_origin_scans_back_when_latest_lacks_field() -> None:
    """La entry más reciente puede no tener `origin`; se sigue buscando hacia atrás."""
    h = History()
    h.append(author="bridge", type="response", content={"origin": "loop_X", "text": "a"})
    h.append(author="u",      type="note",     content={"text": "no origin"})
    h.append(author="u",      type="note",     content={"text": "tampoco"})
    # current_origin debe encontrar "loop_X" aunque no esté en la última.
    assert current_origin(h) == "loop_X"


def test_current_origin_takes_latest_when_multiple_present() -> None:
    """Si varias entries tienen origin, gana la más reciente."""
    h = History()
    h.append(author="bridge", type="r1", content={"origin": "old"})
    h.append(author="bridge", type="r2", content={"origin": "new"})
    assert current_origin(h) == "new"


def test_current_origin_returns_none_when_only_unrelated_entries() -> None:
    h = History()
    h.append(author="u", type="message", content={"text": "hi"})
    h.append(author="u", type="message", content={"text": "bye"})
    assert current_origin(h) is None


# ════════════════════════════════════════════════════════════════════
# current_run_id
# ════════════════════════════════════════════════════════════════════

def test_current_run_id_returns_none_on_empty_history() -> None:
    assert current_run_id(History()) is None


def test_current_run_id_returns_value_from_latest_entry() -> None:
    h = History()
    h.append(author="bridge", type="t", content={"run_id": "run-001"})
    assert current_run_id(h) == "run-001"


def test_current_run_id_scans_back_when_latest_lacks_field() -> None:
    h = History()
    h.append(author="bridge", type="response", content={"run_id": "run-X"})
    h.append(author="u",      type="note",     content={})
    assert current_run_id(h) == "run-X"


def test_current_run_id_takes_latest_when_multiple_present() -> None:
    h = History()
    h.append(author="bridge", type="r1", content={"run_id": "run-001"})
    h.append(author="bridge", type="r2", content={"run_id": "run-002"})
    assert current_run_id(h) == "run-002"


# ════════════════════════════════════════════════════════════════════
# Isolation entre histories
# ════════════════════════════════════════════════════════════════════

def test_queries_isolated_per_history() -> None:
    h1 = History()
    h2 = History()
    h1.append(author="b", type="t", content={"origin": "h1_origin", "run_id": "r1"})
    h2.append(author="b", type="t", content={"origin": "h2_origin", "run_id": "r2"})

    assert current_origin(h1) == "h1_origin"
    assert current_origin(h2) == "h2_origin"
    assert current_run_id(h1) == "r1"
    assert current_run_id(h2) == "r2"


def test_queries_robust_to_non_dict_content() -> None:
    """Si content no es un dict (raro pero permitido por la falta de validación),
    las queries no crashean — devuelven None."""
    h = History()
    # content como dict normal: OK
    h.append(author="u", type="t", content={})
    # current_origin/current_run_id deben devolver None (no hay campo)
    assert current_origin(h) is None
    assert current_run_id(h) is None


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("current_origin_returns_none_on_empty_history",         test_current_origin_returns_none_on_empty_history),
        ("current_origin_returns_value_from_latest_entry_with_origin", test_current_origin_returns_value_from_latest_entry_with_origin),
        ("current_origin_scans_back_when_latest_lacks_field",    test_current_origin_scans_back_when_latest_lacks_field),
        ("current_origin_takes_latest_when_multiple_present",    test_current_origin_takes_latest_when_multiple_present),
        ("current_origin_returns_none_when_only_unrelated_entries", test_current_origin_returns_none_when_only_unrelated_entries),
        ("current_run_id_returns_none_on_empty_history",         test_current_run_id_returns_none_on_empty_history),
        ("current_run_id_returns_value_from_latest_entry",       test_current_run_id_returns_value_from_latest_entry),
        ("current_run_id_scans_back_when_latest_lacks_field",    test_current_run_id_scans_back_when_latest_lacks_field),
        ("current_run_id_takes_latest_when_multiple_present",    test_current_run_id_takes_latest_when_multiple_present),
        ("queries_isolated_per_history",                         test_queries_isolated_per_history),
        ("queries_robust_to_non_dict_content",                   test_queries_robust_to_non_dict_content),
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
