"""
Tests transversales después del PR 5 (cross PR 2 + PR 3 + PR 4 + PR 5).

Verifican que el bridge + History + Monitor + queries trabajan juntos
en escenarios realistas. Simulan lo que el Loop hará en PR 8 (emite
``run_start`` artesanal, llama al bridge, evalúa Monitor).

Dual-mode. Sin LLM ni red.
"""
import sys
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.history.from_run_info import append_entry_from_run
from instantneo.history.queries import (
    current_run_config, current_run_id, current_origin, current_step_num,
)
from instantneo.monitor import Monitor
from instantneo.monitor.conditions import when_type_present, when_last_is_type
from instantneo.monitor.actions import stop_signal, append_note
from instantneo.utils.image_utils import process_images


_TINY_PNG_BYTES = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
    "890000000D49444154789C636000010000000500010D0A2DB40000000049454E"
    "44AE426082"
)


def _mk_run_info(
    *,
    response_content="hi", reasoning=None, error=None,
    tool_executions=None, usage=None,
):
    if usage is None:
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                 "reasoning_tokens": None}
    return SimpleNamespace(
        error=error,
        response_content=response_content,
        reasoning=reasoning,
        finish_reason="stop",
        usage=usage,
        duration_ms=50.0,
        provider="openai", model="gpt-4o-mini",
        timestamp="2026-05-11T12:00:00Z",
        run_params={"model": "gpt-4o-mini", "temperature": 0.7},
        provider_timing=None,
        llm_calls=[SimpleNamespace(response_id="r", response_model="gpt-4o-mini")],
        tool_executions=tool_executions or [],
    )


def _simulate_run_start(h, *, origin, run_id):
    """Helper: simula lo que el Loop emitirá al inicio del run."""
    return h.append(
        author="orchestrator",
        type="run_start",
        content={
            "origin": origin,
            "run_id": run_id,
            "agent":  {"provider": "openai", "model": "gpt-4o-mini"},
            "loop":   {"max_steps": 10},
        },
    )


# ════════════════════════════════════════════════════════════════════
# Bridge + Monitor + queries en pipeline completo
# ════════════════════════════════════════════════════════════════════

def test_full_bridge_flow_with_response_and_tools() -> None:
    """Loop simulado → bridge → entries esperadas en History."""
    h = History()
    _simulate_run_start(h, origin="loop_A", run_id="run-001")

    ri = _mk_run_info(
        tool_executions=[
            SimpleNamespace(name="search", arguments={"q": "x"},
                            result={"hits": 2}, exception=None,
                            execution_mode="wait_response"),
        ],
    )
    h.append_from_run(ri, turn_num=1, author="agent",
                      origin="loop_A", run_id="run-001")

    # Verificar entries
    types = [e.type for e in h.all()]
    assert types == ["run_start", "response", "tool_call"]

    # Bridge estampó origin/run_id en sus entries
    for e in h.all()[1:]:
        assert e.content["origin"] == "loop_A"
        assert e.content["run_id"] == "run-001"


def test_bridge_with_run_error_does_not_emit_response_or_tools() -> None:
    """run-level error short-circuit, no se emiten response ni tools."""
    h = History()
    _simulate_run_start(h, origin="loop_X", run_id="run-err")

    ri = _mk_run_info(
        error="ConnectionError",
        response_content="should not appear",
        tool_executions=[SimpleNamespace(name="t", arguments={}, result=None,
                                          exception=None, execution_mode="wait_response")],
    )
    h.append_from_run(ri, turn_num=1, author="agent",
                      origin="loop_X", run_id="run-err")

    # Solo run_start + 1 error entry
    types = [e.type for e in h.all()]
    assert types == ["run_start", "error"]
    assert h.all()[-1].content["exception"] == "ConnectionError"


def test_monitor_observes_bridged_entries_and_fires_stop_signal() -> None:
    """Pipeline completo: run_start + bridge appendea + Monitor detecta tool exception → stop_signal."""
    h = History()
    _simulate_run_start(h, origin="loop_M", run_id="run-M1")

    # Run con una tool que falló (exception poblada pero el run sobrevive)
    ri = _mk_run_info(
        tool_executions=[
            SimpleNamespace(name="search", arguments={}, result=None,
                            exception="HTTPError 503", execution_mode="wait_response"),
        ],
    )
    h.append_from_run(ri, turn_num=1, author="agent",
                      origin="loop_M", run_id="run-M1")

    # Monitor: si hay tool_call con exception, dispara stop_signal
    from instantneo.monitor.conditions import when_last_content_matches
    has_tool_error = lambda h: any(
        e.type == "tool_call" and e.content.get("exception")
        for e in h.all()
    )

    m = Monitor()
    m.add_rule(has_tool_error, stop_signal("tool falló"))
    m(h)

    signals = h.by_type("stop_signal")
    assert len(signals) == 1
    # Heredó origin/run_id del run_start
    assert signals[0].content["origin"] == "loop_M"
    assert signals[0].content["run_id"] == "run-M1"


def test_stop_signal_inherits_origin_from_run_start_not_bridged_entries() -> None:
    """Confirma el cambio de PR 5: origin viene del run_start canónico,
    no de la entry de bridge más reciente (aunque ambas tengan origin)."""
    h = History()
    # Loop A emite run_start
    _simulate_run_start(h, origin="loop_A", run_id="run-A1")
    # Bridge appendea con esa metadata
    ri = _mk_run_info()
    h.append_from_run(ri, turn_num=1, author="agent",
                      origin="loop_A", run_id="run-A1")
    # Ahora simulamos que appendeamos artesanalmente una entry "bridge-like"
    # con origin distinto, simulando contaminación cruzada
    h.append(author="b", type="response",
             content={"text": "x", "origin": "loop_B", "run_id": "run-B"})

    # stop_signal debería usar el RUN_START (loop_A), no el bridge contaminado
    m = Monitor()
    m.add_rule(lambda h: True, stop_signal("end"))
    m(h)

    sig = h.by_type("stop_signal")[0]
    assert sig.content["origin"] == "loop_A"  # del run_start, no del bridge-like
    assert sig.content["run_id"] == "run-A1"


def test_queries_return_correct_values_post_bridge() -> None:
    """Después del bridge, current_origin/run_id reflejan el run_start vigente."""
    h = History()
    _simulate_run_start(h, origin="loop_Q", run_id="run-Q1")
    ri = _mk_run_info()
    h.append_from_run(ri, turn_num=1, author="agent",
                      origin="loop_Q", run_id="run-Q1")

    assert current_origin(h) == "loop_Q"
    assert current_run_id(h) == "run-Q1"
    cfg = current_run_config(h)
    assert cfg["origin"] == "loop_Q"


# ════════════════════════════════════════════════════════════════════
# Multi-turn: bridge invocado varias veces consecutivas
# ════════════════════════════════════════════════════════════════════

def test_multi_turn_history_via_repeated_bridge_calls() -> None:
    """Simular 3 turnos: cada uno emite step_start (Loop) + bridge."""
    h = History()
    _simulate_run_start(h, origin="loop_T", run_id="run-T1")

    for turn in [1, 2, 3]:
        # Simular step_start (Loop hará esto en PR 8)
        h.append(author="orchestrator", type="step_start",
                 content={"step_num": turn})
        # Bridge appendea response del turn
        ri = _mk_run_info(response_content=f"respuesta turno {turn}")
        h.append_from_run(ri, turn_num=turn, author="agent",
                          origin="loop_T", run_id="run-T1")

    # Verificaciones
    responses = h.by_type("response")
    assert len(responses) == 3
    assert [r.content["text"] for r in responses] == [
        "respuesta turno 1", "respuesta turno 2", "respuesta turno 3",
    ]
    assert [r.content["turn_num"] for r in responses] == [1, 2, 3]
    # current_step_num refleja el último step
    assert current_step_num(h) == 3


# ════════════════════════════════════════════════════════════════════
# Cross PR 1 + PR 5: imagen → bridge → History
# ════════════════════════════════════════════════════════════════════

def test_bridge_with_image_in_arguments_preserves_dict() -> None:
    """Tool con argumento complejo (incluye dict de imagen del PR 1)
    queda preservado intacto a través del bridge."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(_TINY_PNG_BYTES)
    try:
        # Procesa imagen via PR 1
        images = process_images(path, "high")
        # Tool que recibió la imagen como argumento
        ri = _mk_run_info(
            tool_executions=[
                SimpleNamespace(
                    name="analyze_image",
                    arguments={"images": images, "mode": "fast"},
                    result={"objects": ["dog", "ball"]},
                    exception=None, execution_mode="wait_response",
                ),
            ],
        )
        h = History()
        _simulate_run_start(h, origin="loop_img", run_id="run-img-1")
        h.append_from_run(ri, turn_num=1, author="agent",
                          origin="loop_img", run_id="run-img-1")

        tc = h.by_type("tool_call")[0]
        # arguments es dict completo y la imagen sobrevive (con detail)
        assert isinstance(tc.content["arguments"], dict)
        assert tc.content["arguments"]["images"][0]["image_url"]["detail"] == "high"
        # result también nativo
        assert tc.content["result"] == {"objects": ["dog", "ball"]}
    finally:
        os.unlink(path)


# ════════════════════════════════════════════════════════════════════
# Cross PR 4 + PR 5: run_params completo del PR 4 viaja al History
# ════════════════════════════════════════════════════════════════════

def test_bridge_run_params_with_reasoning_persists_in_response_entry() -> None:
    """Snapshot completo de run_params (PR 4) aparece en response entry."""
    h = History()
    _simulate_run_start(h, origin="loop_RP", run_id="run-RP1")

    run_params_snapshot = {
        "model": "o4-mini",
        "temperature": 0.5,
        "reasoning": "high",      # kwarg que pre-PR4 no se capturaba
        "image_detail": "low",
        "custom_thing": 42,
    }
    ri = _mk_run_info()
    ri.run_params = run_params_snapshot
    h.append_from_run(ri, turn_num=1, author="agent",
                      origin="loop_RP", run_id="run-RP1")

    resp = h.by_type("response")[0]
    assert resp.content["run_params"] == run_params_snapshot
    # En particular, reasoning="high" sobrevive (era el caso de prueba del PR 4)
    assert resp.content["run_params"]["reasoning"] == "high"


def test_bridge_reasoning_tokens_in_usage_visible_in_response_entry() -> None:
    """usage.reasoning_tokens (PR 4) sobrevive el bridge al History."""
    h = History()
    _simulate_run_start(h, origin="loop_R", run_id="run-R1")

    ri = _mk_run_info(
        usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
               "reasoning_tokens": 25},
    )
    h.append_from_run(ri, turn_num=1, author="agent",
                      origin="loop_R", run_id="run-R1")
    resp = h.by_type("response")[0]
    assert resp.content["usage"]["reasoning_tokens"] == 25


# ════════════════════════════════════════════════════════════════════
# Vista custom sobre entries del bridge
# ════════════════════════════════════════════════════════════════════

def test_view_renders_bridged_response_with_reasoning() -> None:
    """Vista custom procesa response entries del bridge, incluye reasoning."""
    h = History()
    _simulate_run_start(h, origin="loop_V", run_id="run-V1")
    ri = _mk_run_info(
        response_content="Respuesta final",
        reasoning="Pensé que sería esto porque...",
    )
    h.append_from_run(ri, turn_num=1, author="agent",
                      origin="loop_V", run_id="run-V1")

    @h.view("conversation_with_reasoning")
    def view(history):
        lines = []
        for e in history.by_type("response"):
            lines.append(f"[reasoning] {e.content.get('reasoning', '')}")
            lines.append(f"[text] {e.content['text']}")
        return "\n".join(lines)

    out = h.export("conversation_with_reasoning")
    assert "[reasoning] Pensé que sería esto" in out
    assert "[text] Respuesta final" in out


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("full_bridge_flow_with_response_and_tools",
         test_full_bridge_flow_with_response_and_tools),
        ("bridge_with_run_error_does_not_emit_response_or_tools",
         test_bridge_with_run_error_does_not_emit_response_or_tools),
        ("monitor_observes_bridged_entries_and_fires_stop_signal",
         test_monitor_observes_bridged_entries_and_fires_stop_signal),
        ("stop_signal_inherits_origin_from_run_start_not_bridged_entries",
         test_stop_signal_inherits_origin_from_run_start_not_bridged_entries),
        ("queries_return_correct_values_post_bridge",
         test_queries_return_correct_values_post_bridge),
        ("multi_turn_history_via_repeated_bridge_calls",
         test_multi_turn_history_via_repeated_bridge_calls),
        ("bridge_with_image_in_arguments_preserves_dict",
         test_bridge_with_image_in_arguments_preserves_dict),
        ("bridge_run_params_with_reasoning_persists_in_response_entry",
         test_bridge_run_params_with_reasoning_persists_in_response_entry),
        ("bridge_reasoning_tokens_in_usage_visible_in_response_entry",
         test_bridge_reasoning_tokens_in_usage_visible_in_response_entry),
        ("view_renders_bridged_response_with_reasoning",
         test_view_renders_bridged_response_with_reasoning),
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
