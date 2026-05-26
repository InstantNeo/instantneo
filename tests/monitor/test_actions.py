"""
Tests de ``instantneo.monitor.actions``: built-in actions
(``stop_signal``, ``append_note``).

Dual-mode.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.monitor.actions import stop_signal, append_note


# ════════════════════════════════════════════════════════════════════
# stop_signal
# ════════════════════════════════════════════════════════════════════

def test_stop_signal_appends_entry_with_text() -> None:
    h = History()
    stop_signal("manual_stop")(h)

    assert len(h.all()) == 1
    e = h.all()[0]
    assert e.author == "orchestrator"
    assert e.type == "stop_signal"
    assert e.content["text"] == "manual_stop"


def test_stop_signal_propagates_origin_from_run_start() -> None:
    """Si hay un run_start con origin/run_id, la nueva entry los hereda.

    NOTA (PR 5): cambió respecto del PR 3. Las queries current_origin/
    current_run_id ahora leen SOLO de la entry run_start más reciente
    (spec autoritativa: loop-design.md:1281-1287). Antes escaneaban
    cualquier entry con esos campos.
    """
    h = History()
    h.append(
        author="orchestrator", type="run_start",
        content={
            "origin": "loop_A",
            "run_id": "run-001",
            "agent": {"provider": "openai"},
            "loop":  {"max_steps": 10},
        },
    )

    stop_signal("done")(h)

    new_entry = h.all()[-1]
    assert new_entry.content["origin"] == "loop_A"
    assert new_entry.content["run_id"] == "run-001"


def test_stop_signal_when_no_run_start_origin_run_id_are_none() -> None:
    """Sin entry run_start, los campos origin/run_id quedan en None.

    Caso típico: standalone Monitor sin Loop, o uso post-hoc del History
    sin orquestador. Es degradación documentada — la entry queda igual
    válida, solo sin metadata de auditoría del run.
    """
    h = History()
    # Entries de tipos varios pero ningún run_start
    h.append(author="u", type="random", content={"text": "no origin"})
    h.append(author="bridge", type="response",
             content={"text": "x", "origin": "ignored", "run_id": "ignored"})

    stop_signal("done")(h)

    new_entry = h.all()[-1]
    assert new_entry.type == "stop_signal"
    assert new_entry.content["text"] == "done"
    assert new_entry.content["origin"] is None
    assert new_entry.content["run_id"] is None


def test_stop_signal_uses_latest_run_start_metadata() -> None:
    """Multi-run: gana el run_start más reciente."""
    h = History()
    h.append(
        author="orchestrator", type="run_start",
        content={"origin": "loop_A", "run_id": "run-001"},
    )
    h.append(author="orchestrator", type="run_end", content={})
    h.append(
        author="orchestrator", type="run_start",
        content={"origin": "loop_B", "run_id": "run-002"},
    )

    stop_signal("done")(h)
    last = h.all()[-1]
    assert last.content["origin"] == "loop_B"
    assert last.content["run_id"] == "run-002"


def test_stop_signal_factory_produces_callable() -> None:
    """stop_signal(text) devuelve un callable (no ejecuta nada solo)."""
    action = stop_signal("anything")
    assert callable(action)
    # El action no se ejecutó todavía (no se invocó con un history).
    h = History()
    assert len(h.all()) == 0


def test_stop_signal_on_empty_history() -> None:
    """Llamar stop_signal sobre history vacía produce una entry limpia."""
    h = History()
    stop_signal("first")(h)
    assert len(h.all()) == 1
    e = h.all()[0]
    assert e.id == 1
    assert e.content["text"] == "first"
    assert e.content["origin"] is None
    assert e.content["run_id"] is None


# ════════════════════════════════════════════════════════════════════
# append_note
# ════════════════════════════════════════════════════════════════════

def test_append_note_appends_with_default_author() -> None:
    h = History()
    append_note("checkpoint")(h)

    assert len(h.all()) == 1
    e = h.all()[0]
    assert e.type == "note"
    assert e.author == "orchestrator"
    assert e.content == {"text": "checkpoint"}


def test_append_note_appends_with_custom_author() -> None:
    h = History()
    append_note("info", author="audit_system")(h)

    e = h.all()[0]
    assert e.author == "audit_system"
    assert e.content["text"] == "info"


def test_append_note_factory_produces_callable() -> None:
    action = append_note("x")
    assert callable(action)


def test_append_note_multiple_invocations_accumulate() -> None:
    h = History()
    append_note("a")(h)
    append_note("b")(h)
    append_note("c")(h)

    notes = h.by_type("note")
    assert len(notes) == 3
    assert [n.content["text"] for n in notes] == ["a", "b", "c"]


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("stop_signal_appends_entry_with_text",     test_stop_signal_appends_entry_with_text),
        ("stop_signal_propagates_origin_from_run_start",   test_stop_signal_propagates_origin_from_run_start),
        ("stop_signal_when_no_run_start_origin_run_id_are_none",
         test_stop_signal_when_no_run_start_origin_run_id_are_none),
        ("stop_signal_uses_latest_run_start_metadata",
         test_stop_signal_uses_latest_run_start_metadata),
        ("stop_signal_factory_produces_callable",   test_stop_signal_factory_produces_callable),
        ("stop_signal_on_empty_history",            test_stop_signal_on_empty_history),
        ("append_note_appends_with_default_author", test_append_note_appends_with_default_author),
        ("append_note_appends_with_custom_author",  test_append_note_appends_with_custom_author),
        ("append_note_factory_produces_callable",   test_append_note_factory_produces_callable),
        ("append_note_multiple_invocations_accumulate", test_append_note_multiple_invocations_accumulate),
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
