"""
Tests de ``instantneo.monitor.conditions``: built-in conditions
del rule engine.

Dual-mode (igual que el resto): pytest-compatible + runnable como script.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.monitor.conditions import (
    when_entry_count_above, when_type_count_above, when_author_count_above,
    when_type_present, when_last_is_type, when_last_is_author,
    when_last_content_matches, when_tokens_above,
    every_n_steps, at_step,
    And, Or, Not,
)


# ════════════════════════════════════════════════════════════════════
# Conditions sobre cantidad y tipo
# ════════════════════════════════════════════════════════════════════

def test_when_entry_count_above_true_when_above() -> None:
    h = History()
    h.append(author="u", type="t", content={})
    h.append(author="u", type="t", content={})
    h.append(author="u", type="t", content={})
    assert when_entry_count_above(2)(h) is True


def test_when_entry_count_above_false_when_equal_or_below() -> None:
    h = History()
    h.append(author="u", type="t", content={})
    h.append(author="u", type="t", content={})
    assert when_entry_count_above(2)(h) is False
    assert when_entry_count_above(5)(h) is False


def test_when_type_count_above() -> None:
    h = History()
    h.append(author="u", type="message", content={})
    h.append(author="u", type="message", content={})
    h.append(author="u", type="note", content={})
    assert when_type_count_above("message", 1)(h) is True
    assert when_type_count_above("message", 2)(h) is False
    assert when_type_count_above("note", 0)(h) is True
    assert when_type_count_above("absent", 0)(h) is False


def test_when_author_count_above() -> None:
    h = History()
    h.append(author="A", type="t", content={})
    h.append(author="A", type="t", content={})
    h.append(author="B", type="t", content={})
    assert when_author_count_above("A", 1)(h) is True
    assert when_author_count_above("A", 2)(h) is False
    assert when_author_count_above("B", 0)(h) is True
    assert when_author_count_above("Z", 0)(h) is False


def test_when_type_present_true_when_present() -> None:
    h = History()
    h.append(author="u", type="error", content={})
    assert when_type_present("error")(h) is True


def test_when_type_present_false_when_absent() -> None:
    h = History()
    h.append(author="u", type="message", content={})
    assert when_type_present("error")(h) is False


def test_when_type_present_false_on_empty_history() -> None:
    h = History()
    assert when_type_present("anything")(h) is False


# ════════════════════════════════════════════════════════════════════
# Conditions sobre la última entry
# ════════════════════════════════════════════════════════════════════

def test_when_last_is_type_matches() -> None:
    h = History()
    h.append(author="u", type="message", content={})
    h.append(author="u", type="response", content={})
    assert when_last_is_type("response")(h) is True
    assert when_last_is_type("message")(h) is False


def test_when_last_is_type_on_empty_history() -> None:
    """No crash, devuelve False."""
    assert when_last_is_type("x")(History()) is False


def test_when_last_is_author_matches() -> None:
    h = History()
    h.append(author="A", type="t", content={})
    h.append(author="B", type="t", content={})
    assert when_last_is_author("B")(h) is True
    assert when_last_is_author("A")(h) is False


def test_when_last_is_author_on_empty_history() -> None:
    assert when_last_is_author("X")(History()) is False


def test_when_last_content_matches_with_predicate() -> None:
    h = History()
    h.append(author="u", type="msg", content={"text": "hola"})
    h.append(author="u", type="msg", content={"text": "FINAL"})

    has_final = when_last_content_matches(lambda c: "FINAL" in c.get("text", ""))
    no_final  = when_last_content_matches(lambda c: "absent" in c.get("text", ""))
    assert has_final(h) is True
    assert no_final(h) is False


def test_when_last_content_matches_on_empty_history() -> None:
    assert when_last_content_matches(lambda c: True)(History()) is False


# ════════════════════════════════════════════════════════════════════
# Condition sobre tokens
# ════════════════════════════════════════════════════════════════════

def test_when_tokens_above_default_tokenizer() -> None:
    """Default tokenizer = len(s) // 4. Verifica que cuenta correctamente."""
    h = History()

    @h.view("text")
    def text_view(history):
        return "x" * 100  # 100 chars / 4 = 25 tokens

    assert when_tokens_above("text", 20)(h) is True
    assert when_tokens_above("text", 24)(h) is True
    assert when_tokens_above("text", 25)(h) is False
    assert when_tokens_above("text", 30)(h) is False


def test_when_tokens_above_custom_tokenizer() -> None:
    h = History()

    @h.view("v")
    def v(history):
        return "hola mundo"

    # Tokenizer custom: 1 token por palabra
    by_words = lambda s: len(s.split())
    cond = when_tokens_above("v", 1, tokenizer=by_words)
    assert cond(h) is True
    cond2 = when_tokens_above("v", 2, tokenizer=by_words)
    assert cond2(h) is False


# ════════════════════════════════════════════════════════════════════
# Conditions sobre steps
# ════════════════════════════════════════════════════════════════════

def test_every_n_steps_true_at_multiple() -> None:
    h = History()
    for n in [1, 2, 3, 4, 5, 6]:
        h.append(author="loop", type="step_start", content={"step_num": n})
    assert every_n_steps(3)(h) is True  # step_num=6 es múltiplo de 3


def test_every_n_steps_false_at_non_multiple() -> None:
    h = History()
    for n in [1, 2, 3, 4]:
        h.append(author="loop", type="step_start", content={"step_num": n})
    assert every_n_steps(3)(h) is False  # 4 no es múltiplo de 3


def test_every_n_steps_false_when_no_step_start_entries() -> None:
    """Sin convención del Loop, devuelve False sin crashear."""
    h = History()
    h.append(author="u", type="message", content={})
    assert every_n_steps(1)(h) is False


def test_every_n_steps_false_on_empty_history() -> None:
    assert every_n_steps(5)(History()) is False


def test_every_n_steps_false_when_step_num_zero() -> None:
    """step_num=0 no dispara (la primera pasada no debería disparar la rule)."""
    h = History()
    h.append(author="loop", type="step_start", content={"step_num": 0})
    assert every_n_steps(1)(h) is False


def test_at_step_matches_exact() -> None:
    h = History()
    for n in [1, 2, 3, 4]:
        h.append(author="loop", type="step_start", content={"step_num": n})
    assert at_step(4)(h) is True
    assert at_step(3)(h) is False
    assert at_step(99)(h) is False


def test_at_step_false_on_empty_history() -> None:
    assert at_step(1)(History()) is False


# ════════════════════════════════════════════════════════════════════
# Combinadores
# ════════════════════════════════════════════════════════════════════

def test_and_all_true() -> None:
    h = History()
    h.append(author="u", type="error", content={})
    combined = And(when_type_present("error"), when_entry_count_above(0))
    assert combined(h) is True


def test_and_one_false() -> None:
    h = History()
    h.append(author="u", type="error", content={})
    combined = And(when_type_present("error"), when_type_present("absent"))
    assert combined(h) is False


def test_and_empty_returns_true() -> None:
    """And() sin args: cuantificador universal sobre conjunto vacío."""
    assert And()(History()) is True


def test_or_one_true() -> None:
    h = History()
    h.append(author="u", type="error", content={})
    combined = Or(when_type_present("absent"), when_type_present("error"))
    assert combined(h) is True


def test_or_all_false() -> None:
    h = History()
    h.append(author="u", type="message", content={})
    combined = Or(when_type_present("absent1"), when_type_present("absent2"))
    assert combined(h) is False


def test_or_empty_returns_false() -> None:
    """Or() sin args: cuantificador existencial sobre conjunto vacío."""
    assert Or()(History()) is False


def test_not_negates() -> None:
    h = History()
    assert Not(when_type_present("absent"))(h) is True
    h.append(author="u", type="error", content={})
    assert Not(when_type_present("error"))(h) is False


def test_combinators_compose() -> None:
    """And/Or/Not se componen entre sí sin problemas."""
    h = History()
    h.append(author="u", type="error", content={})
    h.append(author="u", type="warning", content={})

    # (error AND NOT empty) OR absent
    composed = Or(
        And(when_type_present("error"), Not(when_entry_count_above(99))),
        when_type_present("absent"),
    )
    assert composed(h) is True


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("when_entry_count_above_true_when_above", test_when_entry_count_above_true_when_above),
        ("when_entry_count_above_false_when_equal_or_below", test_when_entry_count_above_false_when_equal_or_below),
        ("when_type_count_above",                  test_when_type_count_above),
        ("when_author_count_above",                test_when_author_count_above),
        ("when_type_present_true_when_present",    test_when_type_present_true_when_present),
        ("when_type_present_false_when_absent",    test_when_type_present_false_when_absent),
        ("when_type_present_false_on_empty_history", test_when_type_present_false_on_empty_history),
        ("when_last_is_type_matches",              test_when_last_is_type_matches),
        ("when_last_is_type_on_empty_history",     test_when_last_is_type_on_empty_history),
        ("when_last_is_author_matches",            test_when_last_is_author_matches),
        ("when_last_is_author_on_empty_history",   test_when_last_is_author_on_empty_history),
        ("when_last_content_matches_with_predicate", test_when_last_content_matches_with_predicate),
        ("when_last_content_matches_on_empty_history", test_when_last_content_matches_on_empty_history),
        ("when_tokens_above_default_tokenizer",    test_when_tokens_above_default_tokenizer),
        ("when_tokens_above_custom_tokenizer",     test_when_tokens_above_custom_tokenizer),
        ("every_n_steps_true_at_multiple",         test_every_n_steps_true_at_multiple),
        ("every_n_steps_false_at_non_multiple",    test_every_n_steps_false_at_non_multiple),
        ("every_n_steps_false_when_no_step_start_entries", test_every_n_steps_false_when_no_step_start_entries),
        ("every_n_steps_false_on_empty_history",   test_every_n_steps_false_on_empty_history),
        ("every_n_steps_false_when_step_num_zero", test_every_n_steps_false_when_step_num_zero),
        ("at_step_matches_exact",                  test_at_step_matches_exact),
        ("at_step_false_on_empty_history",         test_at_step_false_on_empty_history),
        ("and_all_true",                           test_and_all_true),
        ("and_one_false",                          test_and_one_false),
        ("and_empty_returns_true",                 test_and_empty_returns_true),
        ("or_one_true",                            test_or_one_true),
        ("or_all_false",                           test_or_all_false),
        ("or_empty_returns_false",                 test_or_empty_returns_false),
        ("not_negates",                            test_not_negates),
        ("combinators_compose",                    test_combinators_compose),
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
