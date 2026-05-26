"""
Tests de ``instantneo.monitor.monitor``: Monitor + MonitorOperations.

Dual-mode (igual que el resto): pytest-compatible + runnable como script.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.monitor import Monitor, MonitorOperations


# ════════════════════════════════════════════════════════════════════
# Monitor — constructor y estado inicial
# ════════════════════════════════════════════════════════════════════

def test_monitor_constructor_default_no_name() -> None:
    m = Monitor()
    assert m.name is None


def test_monitor_constructor_with_name() -> None:
    m = Monitor(name="mon-1")
    assert m.name == "mon-1"


def test_monitor_starts_with_no_rules() -> None:
    m = Monitor()
    # No exponemos _rules como API pública pero verificamos el comportamiento:
    # invocar contra un history vacío no hace nada y no levanta.
    h = History()
    m(h)
    assert h.all() == []


# ════════════════════════════════════════════════════════════════════
# Monitor.add_rule
# ════════════════════════════════════════════════════════════════════

def test_add_rule_increases_rules_count() -> None:
    """add_rule registra una regla — verificamos vía side effect en __call__."""
    m = Monitor()
    fired = []
    m.add_rule(lambda h: True, lambda h: fired.append("a"))
    m(History())
    assert fired == ["a"]


def test_add_rule_appends_in_order() -> None:
    """Varias add_rule preservan el orden de registro."""
    m = Monitor()
    fired = []
    m.add_rule(lambda h: True, lambda h: fired.append("first"))
    m.add_rule(lambda h: True, lambda h: fired.append("second"))
    m.add_rule(lambda h: True, lambda h: fired.append("third"))
    m(History())
    assert fired == ["first", "second", "third"]


# ════════════════════════════════════════════════════════════════════
# Monitor.__call__
# ════════════════════════════════════════════════════════════════════

def test_call_fires_action_when_condition_true() -> None:
    m = Monitor()
    fired = []
    m.add_rule(lambda h: True, lambda h: fired.append("yes"))
    m(History())
    assert fired == ["yes"]


def test_call_skips_action_when_condition_false() -> None:
    m = Monitor()
    fired = []
    m.add_rule(lambda h: False, lambda h: fired.append("no"))
    m(History())
    assert fired == []


def test_call_runs_rules_in_registration_order() -> None:
    """Mixing True/False rules: orden preserva en las que disparan."""
    m = Monitor()
    fired = []
    m.add_rule(lambda h: True, lambda h: fired.append("a"))
    m.add_rule(lambda h: False, lambda h: fired.append("skipped"))
    m.add_rule(lambda h: True, lambda h: fired.append("b"))
    m(History())
    assert fired == ["a", "b"]


def test_action_appends_visible_to_subsequent_rules_in_same_call() -> None:
    """Una action que appendea cambia el estado que la próxima rule observa."""
    m = Monitor()

    def append_marker(h):
        h.append(author="test", type="marker", content={})

    fired_when_marker_present = []
    m.add_rule(lambda h: True, append_marker)
    m.add_rule(
        lambda h: len(h.by_type("marker")) > 0,
        lambda h: fired_when_marker_present.append("yes"),
    )

    h = History()
    m(h)
    # La segunda rule vio el marker que la primera appendeó.
    assert fired_when_marker_present == ["yes"]


def test_monitor_is_callable_as_function() -> None:
    """``monitor(history)`` funciona — el Monitor implementa __call__."""
    m = Monitor()
    fired = []
    m.add_rule(lambda h: True, lambda h: fired.append(1))
    # Sintaxis idiomática: invocar como función.
    m(History())
    assert fired == [1]


def test_call_does_not_catch_action_exceptions() -> None:
    """Si una action levanta, propaga (es bug del caller, no del Monitor)."""
    m = Monitor()

    def bad_action(h):
        raise RuntimeError("oops")

    m.add_rule(lambda h: True, bad_action)
    try:
        m(History())
    except RuntimeError as e:
        assert str(e) == "oops"
        return
    raise AssertionError("Se esperaba RuntimeError propagada")


def test_call_with_no_rules_is_noop() -> None:
    m = Monitor()
    h = History()
    h.append(author="u", type="t", content={})
    m(h)  # no debe modificar nada ni levantar
    assert len(h.all()) == 1


# ════════════════════════════════════════════════════════════════════
# MonitorOperations.union
# ════════════════════════════════════════════════════════════════════

def test_union_combines_rules_in_registration_order() -> None:
    """union(m1, m2) tiene primero las rules de m1 luego las de m2."""
    m1 = Monitor()
    m2 = Monitor()
    fired = []
    m1.add_rule(lambda h: True, lambda h: fired.append("m1-a"))
    m1.add_rule(lambda h: True, lambda h: fired.append("m1-b"))
    m2.add_rule(lambda h: True, lambda h: fired.append("m2-a"))

    combined = MonitorOperations.union(m1, m2)
    combined(History())
    assert fired == ["m1-a", "m1-b", "m2-a"]


def test_union_does_not_mutate_inputs() -> None:
    """Agregar rule al combinado no afecta los originales."""
    m1 = Monitor()
    m2 = Monitor()
    fired_orig = []
    fired_combined = []
    m1.add_rule(lambda h: True, lambda h: fired_orig.append("m1"))

    combined = MonitorOperations.union(m1, m2)
    combined.add_rule(lambda h: True, lambda h: fired_combined.append("new"))

    # Correr m1 solo: la rule del combined NO debe disparar.
    m1(History())
    assert fired_orig == ["m1"]
    assert fired_combined == []


def test_union_with_no_monitors_returns_empty_monitor() -> None:
    """union() sin args devuelve un Monitor vacío."""
    combined = MonitorOperations.union()
    assert isinstance(combined, Monitor)
    h = History()
    combined(h)  # no debe levantar
    assert h.all() == []


def test_union_accepts_optional_name() -> None:
    combined = MonitorOperations.union(name="merged")
    assert combined.name == "merged"


def test_union_single_monitor_copies_rules() -> None:
    """union(m) con un solo monitor produce uno con las mismas rules."""
    m = Monitor()
    fired = []
    m.add_rule(lambda h: True, lambda h: fired.append("x"))

    combined = MonitorOperations.union(m)
    combined(History())
    assert fired == ["x"]


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("monitor_constructor_default_no_name",  test_monitor_constructor_default_no_name),
        ("monitor_constructor_with_name",        test_monitor_constructor_with_name),
        ("monitor_starts_with_no_rules",         test_monitor_starts_with_no_rules),
        ("add_rule_increases_rules_count",       test_add_rule_increases_rules_count),
        ("add_rule_appends_in_order",            test_add_rule_appends_in_order),
        ("call_fires_action_when_condition_true", test_call_fires_action_when_condition_true),
        ("call_skips_action_when_condition_false", test_call_skips_action_when_condition_false),
        ("call_runs_rules_in_registration_order", test_call_runs_rules_in_registration_order),
        ("action_appends_visible_to_subsequent_rules_in_same_call",
         test_action_appends_visible_to_subsequent_rules_in_same_call),
        ("monitor_is_callable_as_function",      test_monitor_is_callable_as_function),
        ("call_does_not_catch_action_exceptions", test_call_does_not_catch_action_exceptions),
        ("call_with_no_rules_is_noop",           test_call_with_no_rules_is_noop),
        ("union_combines_rules_in_registration_order", test_union_combines_rules_in_registration_order),
        ("union_does_not_mutate_inputs",         test_union_does_not_mutate_inputs),
        ("union_with_no_monitors_returns_empty_monitor", test_union_with_no_monitors_returns_empty_monitor),
        ("union_accepts_optional_name",          test_union_accepts_optional_name),
        ("union_single_monitor_copies_rules",    test_union_single_monitor_copies_rules),
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
