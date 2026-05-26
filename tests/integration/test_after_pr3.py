"""
Tests transversales después del PR 3 (cross PR 1 + PR 2 + PR 3).

Verifican que el Monitor (PR 3), el History (PR 2) y los helpers de
imágenes (PR 1) interactúan correctamente en escenarios realistas.

Dual-mode. No requieren red ni LLM.
"""
import sys
import os
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.monitor import Monitor, MonitorOperations
from instantneo.monitor.conditions import (
    when_type_present, when_tokens_above, every_n_steps, And,
)
from instantneo.monitor.actions import stop_signal, append_note
from instantneo.utils.image_utils import process_images


_TINY_PNG_BYTES = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
    "890000000D49444154789C636000010000000500010D0A2DB40000000049454E"
    "44AE426082"
)


def _write_tiny_png() -> str:
    fd, path = tempfile.mkstemp(suffix=".png")
    with os.fdopen(fd, "wb") as f:
        f.write(_TINY_PNG_BYTES)
    return path


# ════════════════════════════════════════════════════════════════════
# Monitor + History en patrones realistas
# ════════════════════════════════════════════════════════════════════

def test_monitor_observes_real_history_and_appends_via_action() -> None:
    """Escenario canónico del doc: Monitor con stop_signal cuando aparece 'error'."""
    h = History()
    m = Monitor()
    m.add_rule(when_type_present("error"), stop_signal("se detectó un error"))

    # No hay errores aún
    m(h)
    assert len(h.all()) == 0

    # Aparece un error
    h.append(author="agent", type="error", content={"exception": "ConnectionError"})
    m(h)

    # El stop_signal debe haberse appendeado
    signals = h.by_type("stop_signal")
    assert len(signals) == 1
    assert signals[0].content["text"] == "se detectó un error"


def test_stop_signal_action_propagates_origin_and_run_id_from_run_start() -> None:
    """stop_signal hereda origin/run_id del run_start vigente.

    NOTA (PR 5): cambió respecto del PR 3. Las queries derivan de run_start
    (spec autoritativa), no de cualquier entry con esos campos.
    """
    h = History()
    # Simular Loop: emite run_start con la metadata del run
    h.append(
        author="orchestrator",
        type="run_start",
        content={"origin": "loop_alpha", "run_id": "run-42",
                 "agent": {}, "loop": {}},
    )
    # El bridge ya appendea con esa metadata, pero acá vamos directo
    # a una rule que dispara stop_signal y verifica que hereda.

    m = Monitor()
    m.add_rule(lambda h: True, stop_signal("done"))
    m(h)

    signal = h.by_type("stop_signal")[0]
    assert signal.content["text"]   == "done"
    assert signal.content["origin"] == "loop_alpha"
    assert signal.content["run_id"] == "run-42"


def test_multiple_monitors_on_same_history_compose_via_union() -> None:
    """Dos monitors temáticos combinados con union — ambas rules disparan."""
    audit = Monitor(name="audit")
    notes_log: list = []
    audit.add_rule(
        when_type_present("error"),
        lambda h: notes_log.append("audit_saw_error"),
    )

    alerts = Monitor(name="alerts")
    alerts.add_rule(
        when_type_present("error"),
        lambda h: notes_log.append("alerts_fired"),
    )

    combined = MonitorOperations.union(audit, alerts)
    h = History()
    h.append(author="agent", type="error", content={"e": "x"})
    combined(h)

    assert "audit_saw_error" in notes_log
    assert "alerts_fired" in notes_log


def test_view_on_history_used_by_when_tokens_above() -> None:
    """Vista + when_tokens_above: la condition dispara cuando crece la vista."""
    h = History()

    @h.view("simple_text")
    def simple_text(history):
        return " ".join(
            e.content.get("text", "")
            for e in history.all()
        )

    m = Monitor()
    fired: list = []
    # Default tokenizer = len(s) // 4
    m.add_rule(when_tokens_above("simple_text", 10), lambda h: fired.append("over"))

    # 1 entry corta → ~3 tokens
    h.append(author="u", type="msg", content={"text": "hola"})
    m(h)
    assert fired == []

    # Crece la vista
    for _ in range(20):
        h.append(author="u", type="msg", content={"text": "lorem ipsum dolor sit amet"})
    m(h)
    assert fired == ["over"]


def test_monitor_call_is_idempotent_only_in_state_not_in_actions() -> None:
    """Documenta semántica: el Monitor no recuerda qué disparó antes.

    Si invocás el monitor dos veces sin cambiar el state, las rules
    pueden disparar dos veces. Esto es comportamiento esperado —
    cada invocación es independiente."""
    h = History()
    h.append(author="u", type="error", content={"e": "x"})

    m = Monitor()
    m.add_rule(when_type_present("error"), append_note("error_seen"))

    m(h)
    m(h)
    m(h)
    notes = h.by_type("note")
    assert len(notes) == 3   # Dispara cada vez. Sin memoria.


def test_history_reset_then_monitor_evaluation_on_empty() -> None:
    """Después de reset(), una pasada del monitor no debe crashear ni disparar
    rules basadas en entries."""
    h = History()
    h.append(author="u", type="error", content={"e": "x"})

    m = Monitor()
    fired: list = []
    m.add_rule(when_type_present("error"), lambda h: fired.append("triggered"))

    m(h)
    assert fired == ["triggered"]

    h.reset()
    m(h)
    # No debe haber sumado otro trigger
    assert fired == ["triggered"]


# ════════════════════════════════════════════════════════════════════
# Cross PR 1 + PR 2 + PR 3: imagen → entry → monitor
# ════════════════════════════════════════════════════════════════════

def test_image_pipeline_with_monitor() -> None:
    """Pipeline completo: process_images (PR 1) → append a History (PR 2) →
    Monitor detecta entry con imágenes y dispara append_note (PR 3)."""
    path = _write_tiny_png()
    try:
        # PR 1
        images = process_images(path, "high")
        assert images[0]["image_url"]["detail"] == "high"

        # PR 2: appendear en una entry
        h = History()
        h.append(
            author="bridge",
            type="prompt",
            content={"text": "describe", "images": images},
        )

        # PR 3: Monitor con condition custom que detecta entries con imágenes.
        # Usamos when_last_content_matches con un predicate que detecta "images"
        from instantneo.monitor.conditions import when_last_content_matches
        has_images = when_last_content_matches(lambda c: "images" in c)
        m = Monitor()
        m.add_rule(has_images, append_note("entry con imágenes detectada"))

        m(h)
        notes = h.by_type("note")
        assert len(notes) == 1
        assert notes[0].content["text"] == "entry con imágenes detectada"
    finally:
        os.unlink(path)


def test_monitor_acts_on_history_with_image_entries_and_signals_stop() -> None:
    """Variante: rule basada en imágenes dispara stop_signal.

    NOTA (PR 5): el origin/run_id de la stop_signal vienen de run_start,
    no de la entry de imagen (spec autoritativa).
    """
    path = _write_tiny_png()
    try:
        images = process_images(path, "low")

        h = History()
        # Loop simulado: run_start con metadata canónica
        h.append(
            author="orchestrator",
            type="run_start",
            content={"origin": "loop_image", "run_id": "run-img-1",
                     "agent": {}, "loop": {}},
        )
        # Bridge simulado: entry de prompt con imágenes
        h.append(
            author="bridge",
            type="prompt",
            content={
                "text": "analiza",
                "images": images,
                "origin": "loop_image",
                "run_id": "run-img-1",
            },
        )

        from instantneo.monitor.conditions import when_last_content_matches
        has_images = when_last_content_matches(lambda c: "images" in c)

        m = Monitor()
        m.add_rule(has_images, stop_signal("imagen procesada, parar"))

        m(h)

        signals = h.by_type("stop_signal")
        assert len(signals) == 1
        sig = signals[0]
        assert sig.content["text"] == "imagen procesada, parar"
        # Heredó origin y run_id del run_start
        assert sig.content["origin"] == "loop_image"
        assert sig.content["run_id"] == "run-img-1"
    finally:
        os.unlink(path)


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("monitor_observes_real_history_and_appends_via_action",
         test_monitor_observes_real_history_and_appends_via_action),
        ("stop_signal_action_propagates_origin_and_run_id_from_run_start",
         test_stop_signal_action_propagates_origin_and_run_id_from_run_start),
        ("multiple_monitors_on_same_history_compose_via_union",
         test_multiple_monitors_on_same_history_compose_via_union),
        ("view_on_history_used_by_when_tokens_above",
         test_view_on_history_used_by_when_tokens_above),
        ("monitor_call_is_idempotent_only_in_state_not_in_actions",
         test_monitor_call_is_idempotent_only_in_state_not_in_actions),
        ("history_reset_then_monitor_evaluation_on_empty",
         test_history_reset_then_monitor_evaluation_on_empty),
        ("image_pipeline_with_monitor",
         test_image_pipeline_with_monitor),
        ("monitor_acts_on_history_with_image_entries_and_signals_stop",
         test_monitor_acts_on_history_with_image_entries_and_signals_stop),
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
