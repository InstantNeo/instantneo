"""
Tests de ``instantneo.history.queries``: 4 helpers (current_run_config,
current_run_id, current_origin, current_step_num).

Doc rector: docs/design/loop-design.md sección "Helpers necesarios"
(líneas 1267-1294). Todas las queries derivan de las entries
``run_start`` y ``step_start`` que el Loop emite — no escanean
cualquier entry.

NOTA HISTÓRICA: en PR 3 (commit 35ec75c) la implementación inicial
escaneaba cualquier entry con ``content["origin"]``/``content["run_id"]``.
Ese comportamiento no seguía la spec autoritativa. PR 5 corrige y
estos tests fueron reescritos.

Dual-mode.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.history.queries import (
    current_run_config, current_run_id, current_origin, current_step_num,
)


# ════════════════════════════════════════════════════════════════════
# current_run_config
# ════════════════════════════════════════════════════════════════════

def test_current_run_config_returns_none_on_empty_history() -> None:
    assert current_run_config(History()) is None


def test_current_run_config_returns_none_when_no_run_start_present() -> None:
    """History con entries de otros tipos pero ningún run_start → None."""
    h = History()
    h.append(author="agent", type="response",
             content={"text": "hi", "origin": "loop_X", "run_id": "r1"})
    h.append(author="u", type="note", content={"text": "nota"})
    assert current_run_config(h) is None


def test_current_run_config_returns_content_of_latest_run_start() -> None:
    """Devuelve el dict completo del último run_start."""
    h = History()
    h.append(
        author="orchestrator",
        type="run_start",
        content={
            "origin": "loop_A",
            "run_id": "run-001",
            "agent": {"provider": "openai", "model": "gpt-4o"},
            "loop":  {"max_steps": 20},
        },
    )
    cfg = current_run_config(h)
    assert isinstance(cfg, dict)
    assert cfg["origin"] == "loop_A"
    assert cfg["run_id"] == "run-001"
    assert cfg["agent"]["model"] == "gpt-4o"


def test_current_run_config_takes_latest_when_multiple_runs() -> None:
    """Con varios run_start (multi-run), gana el más reciente."""
    h = History()
    h.append(author="o", type="run_start",
             content={"origin": "loop_A", "run_id": "run-001"})
    h.append(author="o", type="run_end", content={})
    h.append(author="o", type="run_start",
             content={"origin": "loop_B", "run_id": "run-002"})
    cfg = current_run_config(h)
    assert cfg["origin"] == "loop_B"
    assert cfg["run_id"] == "run-002"


def test_current_run_config_ignores_non_run_start_entries() -> None:
    """Solo escanea by_type('run_start'), entries de bridge no cuentan."""
    h = History()
    # Entry de bridge con origin/run_id, pero NO es run_start
    h.append(author="bridge", type="response",
             content={"text": "x", "origin": "bridge_origin", "run_id": "bridge_run"})
    assert current_run_config(h) is None


# ════════════════════════════════════════════════════════════════════
# current_run_id
# ════════════════════════════════════════════════════════════════════

def test_current_run_id_returns_none_on_empty_history() -> None:
    assert current_run_id(History()) is None


def test_current_run_id_returns_none_without_run_start() -> None:
    h = History()
    h.append(author="b", type="response",
             content={"origin": "x", "run_id": "y"})
    assert current_run_id(h) is None


def test_current_run_id_returns_run_id_of_latest_run_start() -> None:
    h = History()
    h.append(author="o", type="run_start",
             content={"origin": "loop_A", "run_id": "run-001"})
    assert current_run_id(h) == "run-001"


def test_current_run_id_takes_latest_when_multiple_run_starts() -> None:
    h = History()
    h.append(author="o", type="run_start", content={"run_id": "first"})
    h.append(author="o", type="run_start", content={"run_id": "second"})
    assert current_run_id(h) == "second"


def test_current_run_id_returns_none_when_run_start_lacks_run_id() -> None:
    """run_start sin run_id → None (case edge defensivo)."""
    h = History()
    h.append(author="o", type="run_start", content={"origin": "x"})
    assert current_run_id(h) is None


# ════════════════════════════════════════════════════════════════════
# current_origin
# ════════════════════════════════════════════════════════════════════

def test_current_origin_returns_none_on_empty_history() -> None:
    assert current_origin(History()) is None


def test_current_origin_returns_none_without_run_start() -> None:
    h = History()
    h.append(author="b", type="response",
             content={"origin": "should-be-ignored"})
    assert current_origin(h) is None


def test_current_origin_returns_origin_of_latest_run_start() -> None:
    h = History()
    h.append(author="o", type="run_start",
             content={"origin": "loop_alpha", "run_id": "r"})
    assert current_origin(h) == "loop_alpha"


def test_current_origin_takes_latest_when_multiple_run_starts() -> None:
    h = History()
    h.append(author="o", type="run_start", content={"origin": "first_loop"})
    h.append(author="o", type="run_start", content={"origin": "second_loop"})
    assert current_origin(h) == "second_loop"


def test_current_origin_returns_none_when_run_start_lacks_origin() -> None:
    h = History()
    h.append(author="o", type="run_start", content={"run_id": "x"})
    assert current_origin(h) is None


# ════════════════════════════════════════════════════════════════════
# current_step_num
# ════════════════════════════════════════════════════════════════════

def test_current_step_num_returns_none_on_empty_history() -> None:
    assert current_step_num(History()) is None


def test_current_step_num_returns_none_without_step_start() -> None:
    """History con entries pero ninguna step_start → None."""
    h = History()
    h.append(author="o", type="run_start", content={"origin": "x"})
    h.append(author="agent", type="response", content={"text": "hi"})
    assert current_step_num(h) is None


def test_current_step_num_returns_value_from_latest_step_start() -> None:
    h = History()
    for i in [1, 2, 3]:
        h.append(author="loop", type="step_start", content={"step_num": i})
    assert current_step_num(h) == 3


def test_current_step_num_handles_non_int_step_num() -> None:
    """Si step_num por error no es int, devuelve None (defensivo)."""
    h = History()
    h.append(author="loop", type="step_start", content={"step_num": "not_int"})
    assert current_step_num(h) is None


def test_current_step_num_handles_missing_step_num_key() -> None:
    """step_start sin step_num en content → None."""
    h = History()
    h.append(author="loop", type="step_start", content={"other": "data"})
    assert current_step_num(h) is None


def test_current_step_num_ignores_non_step_start_entries() -> None:
    h = History()
    h.append(author="x", type="something_else", content={"step_num": 99})
    assert current_step_num(h) is None


# ════════════════════════════════════════════════════════════════════
# Isolation
# ════════════════════════════════════════════════════════════════════

def test_queries_isolated_per_history() -> None:
    h1 = History()
    h2 = History()
    h1.append(author="o", type="run_start",
              content={"origin": "h1_loop", "run_id": "h1_run"})
    h2.append(author="o", type="run_start",
              content={"origin": "h2_loop", "run_id": "h2_run"})

    assert current_origin(h1) == "h1_loop"
    assert current_origin(h2) == "h2_loop"
    assert current_run_id(h1) == "h1_run"
    assert current_run_id(h2) == "h2_run"


def test_queries_robust_to_non_dict_content_in_run_start() -> None:
    """Defensivo: si por error un run_start tiene content no-dict,
    no crashear (devolver None es preferible a crashear)."""
    # Esto en práctica no debería pasar (History.append exige content: dict),
    # pero el helper igual no debería romperse.
    h = History()
    h.append(author="o", type="run_start", content={})  # dict vacío, sin origin/run_id
    assert current_origin(h) is None
    assert current_run_id(h) is None


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # current_run_config
        ("current_run_config_returns_none_on_empty_history",
         test_current_run_config_returns_none_on_empty_history),
        ("current_run_config_returns_none_when_no_run_start_present",
         test_current_run_config_returns_none_when_no_run_start_present),
        ("current_run_config_returns_content_of_latest_run_start",
         test_current_run_config_returns_content_of_latest_run_start),
        ("current_run_config_takes_latest_when_multiple_runs",
         test_current_run_config_takes_latest_when_multiple_runs),
        ("current_run_config_ignores_non_run_start_entries",
         test_current_run_config_ignores_non_run_start_entries),
        # current_run_id
        ("current_run_id_returns_none_on_empty_history",
         test_current_run_id_returns_none_on_empty_history),
        ("current_run_id_returns_none_without_run_start",
         test_current_run_id_returns_none_without_run_start),
        ("current_run_id_returns_run_id_of_latest_run_start",
         test_current_run_id_returns_run_id_of_latest_run_start),
        ("current_run_id_takes_latest_when_multiple_run_starts",
         test_current_run_id_takes_latest_when_multiple_run_starts),
        ("current_run_id_returns_none_when_run_start_lacks_run_id",
         test_current_run_id_returns_none_when_run_start_lacks_run_id),
        # current_origin
        ("current_origin_returns_none_on_empty_history",
         test_current_origin_returns_none_on_empty_history),
        ("current_origin_returns_none_without_run_start",
         test_current_origin_returns_none_without_run_start),
        ("current_origin_returns_origin_of_latest_run_start",
         test_current_origin_returns_origin_of_latest_run_start),
        ("current_origin_takes_latest_when_multiple_run_starts",
         test_current_origin_takes_latest_when_multiple_run_starts),
        ("current_origin_returns_none_when_run_start_lacks_origin",
         test_current_origin_returns_none_when_run_start_lacks_origin),
        # current_step_num
        ("current_step_num_returns_none_on_empty_history",
         test_current_step_num_returns_none_on_empty_history),
        ("current_step_num_returns_none_without_step_start",
         test_current_step_num_returns_none_without_step_start),
        ("current_step_num_returns_value_from_latest_step_start",
         test_current_step_num_returns_value_from_latest_step_start),
        ("current_step_num_handles_non_int_step_num",
         test_current_step_num_handles_non_int_step_num),
        ("current_step_num_handles_missing_step_num_key",
         test_current_step_num_handles_missing_step_num_key),
        ("current_step_num_ignores_non_step_start_entries",
         test_current_step_num_ignores_non_step_start_entries),
        # isolation
        ("queries_isolated_per_history",
         test_queries_isolated_per_history),
        ("queries_robust_to_non_dict_content_in_run_start",
         test_queries_robust_to_non_dict_content_in_run_start),
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
