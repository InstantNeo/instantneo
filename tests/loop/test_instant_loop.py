"""
Tests de ``InstantLoop`` (PR 8).

Cubre stop conditions, freshness filter, sugar stop_tool, integración
con Monitor, debug=True, errores.

Mocks: el agente se simula con SimpleNamespace + run_info sintético.
Permite testear el Loop sin red ni LLM.
"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.loop import InstantLoop, RunResult, RenderedPrompt, RunLog, LoopConfigError
from instantneo.monitor import Monitor
from instantneo.monitor.conditions import when_type_present, when_last_tool_called
from instantneo.monitor.actions import stop_signal


# ────────────────────────────────────────────────────────────────────
# Mock InstantNeo
# ────────────────────────────────────────────────────────────────────

class _MockCaps:
    def __init__(self, schemas=None):
        self._schemas = schemas or []
    def get_schemas(self):
        return list(self._schemas)


def _mk_run_info(*, error=None, response_content="resp",
                  tool_executions=None, reasoning=None):
    return SimpleNamespace(
        error=error, prompt="",
        response_content=response_content,
        reasoning=reasoning,
        finish_reason="stop",
        usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8, "reasoning_tokens": 0},
        duration_ms=10.0,
        provider="mock", model="mock-m",
        timestamp="2026-05-11T10:00:00Z",
        run_params={"model": "mock-m"},
        provider_timing=None,
        llm_calls=[SimpleNamespace(
            messages_sent=[], response_content=response_content,
            finish_reason="stop", tool_calls_requested=[],
            usage=None, response_id="rid", response_model="m",
            reasoning_content=reasoning, raw_response=None,
        )],
        tool_executions=tool_executions or [],
        messages_sent=[],
    )


def _mk_mock_agent(*, schemas=None, run_info_factory=None, raise_on_call=False):
    """Construye un mock de InstantNeo.

    run_info_factory: callable opcional para producir RunInfo en cada call;
    si None, usa default response. Recibe (prompt, count) y devuelve RunInfo.
    """
    class _Agent:
        def __init__(self):
            self.config = SimpleNamespace(
                provider="mock", model="mock-m",
                api_key="sk-MOCK", role_setup="x",
                temperature=None, max_tokens=None,
                presence_penalty=None, frequency_penalty=None,
                stop=None, seed=None, stream=False, logit_bias=None,
                images=None, image_detail=None,
                location=None, service_account_file=None,
            )
            self.capabilities = _MockCaps(schemas)
            self.last_run = None
            self._call_count = 0
        def get_resolved_role_setup(self, shelf_context=None):
            return "Mocked role_setup"
        def run(self, prompt, images=None, image_detail=None):
            self._call_count += 1
            if raise_on_call:
                raise RuntimeError("simulated agent crash")
            if run_info_factory is not None:
                self.last_run = run_info_factory(prompt, self._call_count)
            else:
                self.last_run = _mk_run_info(
                    response_content=f"Mock response #{self._call_count}"
                )
    return _Agent()


# ════════════════════════════════════════════════════════════════════
# Construcción y validaciones
# ════════════════════════════════════════════════════════════════════

def test_construct_with_minimal_args() -> None:
    loop = InstantLoop(agent=_mk_mock_agent())
    assert isinstance(loop.history, History)
    assert loop.max_steps == 30
    assert loop.name.startswith("loop_")
    assert loop.debug is False


def test_construct_with_existing_history() -> None:
    h = History(name="shared")
    loop = InstantLoop(agent=_mk_mock_agent(), history=h)
    assert loop.history is h


def test_construct_with_custom_name() -> None:
    loop = InstantLoop(agent=_mk_mock_agent(), name="investigador")
    assert loop.name == "investigador"


def test_construct_rejects_negative_max_steps() -> None:
    try:
        InstantLoop(agent=_mk_mock_agent(), max_steps=-1)
    except LoopConfigError:
        return
    raise AssertionError("Esperaba LoopConfigError")


def test_construct_rejects_non_int_max_steps() -> None:
    try:
        InstantLoop(agent=_mk_mock_agent(), max_steps="10")  # type: ignore
    except LoopConfigError:
        return
    raise AssertionError("Esperaba LoopConfigError")


def test_construct_max_steps_zero_allowed() -> None:
    loop = InstantLoop(agent=_mk_mock_agent(), max_steps=0)
    assert loop.max_steps == 0


def test_construct_view_unknown_raises() -> None:
    try:
        InstantLoop(agent=_mk_mock_agent(), view="no_existe")
    except LoopConfigError as e:
        assert "no_existe" in str(e)
        return
    raise AssertionError("Esperaba LoopConfigError")


def test_construct_auto_registers_loop_default_view() -> None:
    h = History()
    assert not h.has_view("loop_default")
    InstantLoop(agent=_mk_mock_agent(), history=h)
    assert h.has_view("loop_default")


def test_construct_does_not_overwrite_existing_view() -> None:
    """Si el History ya tiene 'loop_default', el Loop NO la pisa."""
    h = History()
    sentinel = lambda hist: "CUSTOM"
    h.add_view("loop_default", sentinel)
    InstantLoop(agent=_mk_mock_agent(), history=h)
    # La vista sigue siendo la custom
    assert h.export("loop_default") == "CUSTOM"


# ════════════════════════════════════════════════════════════════════
# Run básico
# ════════════════════════════════════════════════════════════════════

def test_run_returns_run_result() -> None:
    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, max_steps=1)
    result = loop.run("hola")
    assert isinstance(result, RunResult)
    assert isinstance(result.history, History)
    assert isinstance(result.run_id, str)
    assert result.terminated_reason == "max_steps"


def test_run_emits_run_start_and_run_end() -> None:
    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, max_steps=1)
    loop.run("hola")
    assert len(loop.history.by_type("run_start")) == 1
    assert len(loop.history.by_type("run_end")) == 1


def test_run_emits_prompt_entry() -> None:
    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, max_steps=1)
    loop.run("query inicial")
    prompts = loop.history.by_type("prompt")
    assert len(prompts) == 1
    assert prompts[0].content["text"] == "query inicial"


def test_run_emits_step_start_step_end_per_step() -> None:
    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, max_steps=3)
    loop.run("hola")
    assert len(loop.history.by_type("step_start")) == 3
    assert len(loop.history.by_type("step_end")) == 3


def test_run_bridge_appends_response_entries() -> None:
    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, max_steps=2)
    loop.run("hola")
    responses = loop.history.by_type("response")
    assert len(responses) == 2


def test_run_origin_set_on_orchestrator_entries() -> None:
    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, name="my_loop", max_steps=1)
    loop.run("hola")
    for e in loop.history.all():
        if e.author == "orchestrator":
            assert e.content.get("origin") == "my_loop"


# ════════════════════════════════════════════════════════════════════
# Stop conditions
# ════════════════════════════════════════════════════════════════════

def test_max_steps_terminates_when_no_other_stop() -> None:
    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, max_steps=2)
    result = loop.run("hola")
    assert result.terminated_reason == "max_steps"
    assert result.total_steps == 2
    assert result.stop_reason is None


def test_max_steps_zero_means_no_cap() -> None:
    """Con max_steps=0 y un monitor que para, el Loop respeta el monitor."""
    agent = _mk_mock_agent()
    mon = Monitor()
    mon.add_rule(when_type_present("response"), stop_signal("listo"))
    loop = InstantLoop(agent=agent, monitors=mon,
                       stop_signals=["listo"], max_steps=0)
    result = loop.run("hola")
    assert result.terminated_reason == "stop_signal"
    assert result.total_steps == 1


def test_stop_signal_via_monitor() -> None:
    agent = _mk_mock_agent()
    mon = Monitor()
    mon.add_rule(when_type_present("response"), stop_signal("done"))
    loop = InstantLoop(agent=agent, monitors=mon,
                       stop_signals=["done"], max_steps=10)
    result = loop.run("hola")
    assert result.terminated_reason == "stop_signal"
    assert result.stop_reason == "done"


def test_loop_stop_external() -> None:
    """loop.stop(reason) llamado dentro de monitor → terminated_reason=external."""
    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, max_steps=10)
    mon = Monitor()
    def cancel(history):
        loop.stop("timeout-test")
    mon.add_rule(lambda h: True, cancel)
    loop.monitor = mon
    result = loop.run("hola")
    assert result.terminated_reason == "external"
    assert result.stop_reason == "timeout-test"


def test_view_can_short_circuit_with_stop_reason() -> None:
    """Vista devolviendo RenderedPrompt con stop_reason rompe antes del agente."""
    h = History()
    @h.view("stop_immediately")
    def stop_view(history):
        return RenderedPrompt(text="...", stop_reason="too soon")

    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, history=h, view="stop_immediately", max_steps=10)
    result = loop.run("hola")
    assert result.terminated_reason == "view"
    assert result.stop_reason == "too soon"
    assert result.total_steps == 0


# ════════════════════════════════════════════════════════════════════
# Sugar stop_tool
# ════════════════════════════════════════════════════════════════════

def test_stop_tool_single_name() -> None:
    """stop_tool='finalizar' debe parar cuando el agente llama esa tool."""
    def factory(prompt, count):
        return _mk_run_info(
            response_content=None,
            tool_executions=[SimpleNamespace(
                name="finalizar", arguments={}, result={"ok": True},
                exception=None, execution_mode="wait_response",
            )],
        )
    agent = _mk_mock_agent(run_info_factory=factory)
    loop = InstantLoop(agent=agent, stop_tool="finalizar", max_steps=10)
    result = loop.run("hola")
    assert result.terminated_reason == "stop_signal"
    assert result.stop_reason == "agent called finalizar"


def test_stop_tool_multiple_names() -> None:
    def factory(prompt, count):
        return _mk_run_info(
            response_content=None,
            tool_executions=[SimpleNamespace(
                name="submit", arguments={}, result={},
                exception=None, execution_mode="wait_response",
            )],
        )
    agent = _mk_mock_agent(run_info_factory=factory)
    loop = InstantLoop(agent=agent, stop_tool=["finalizar", "submit", "abort"], max_steps=10)
    result = loop.run("hola")
    assert result.terminated_reason == "stop_signal"
    assert result.stop_reason == "agent called submit"


def test_stop_tool_does_not_fire_for_other_tools() -> None:
    """Si el agente llama una tool distinta, NO se dispara stop."""
    def factory(prompt, count):
        return _mk_run_info(
            response_content="resp",
            tool_executions=[SimpleNamespace(
                name="otra_tool", arguments={}, result={},
                exception=None, execution_mode="wait_response",
            )],
        )
    agent = _mk_mock_agent(run_info_factory=factory)
    loop = InstantLoop(agent=agent, stop_tool="finalizar", max_steps=2)
    result = loop.run("hola")
    # Llega a max_steps, no stop_signal
    assert result.terminated_reason == "max_steps"


# ════════════════════════════════════════════════════════════════════
# Freshness filter
# ════════════════════════════════════════════════════════════════════

def test_freshness_filter_ignores_old_stop_signals() -> None:
    """stop_signal viejo (de un run anterior) no dispara en el nuevo run."""
    h = History()
    h.append(author="o", type="stop_signal", content={"text": "obsoleto"})

    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, history=h,
                       stop_signals=["obsoleto"], max_steps=2)
    result = loop.run("hola")
    # El signal viejo (id=1) está antes del run_start nuevo → ignorado
    assert result.terminated_reason == "max_steps"


def test_freshness_filter_catches_signal_during_run() -> None:
    """stop_signal appendeado durante el run SÍ dispara."""
    h = History()
    agent = _mk_mock_agent()
    mon = Monitor()
    mon.add_rule(when_type_present("response"), stop_signal("fresco"))
    loop = InstantLoop(agent=agent, history=h, monitors=mon,
                       stop_signals=["fresco"], max_steps=10)
    result = loop.run("hola")
    assert result.terminated_reason == "stop_signal"
    assert result.stop_reason == "fresco"


# ════════════════════════════════════════════════════════════════════
# Errores
# ════════════════════════════════════════════════════════════════════

def test_agent_exception_caught_and_emits_error_entry() -> None:
    agent = _mk_mock_agent(raise_on_call=True)
    loop = InstantLoop(agent=agent, max_steps=2)
    result = loop.run("hola")
    assert result.terminated_reason == "error"
    errors = loop.history.by_type("error")
    assert len(errors) >= 1


def test_monitor_action_exception_caught() -> None:
    agent = _mk_mock_agent()
    mon = Monitor()
    def boom(history):
        raise RuntimeError("monitor boom")
    mon.add_rule(lambda h: True, boom)
    loop = InstantLoop(agent=agent, monitors=mon, max_steps=2)
    result = loop.run("hola")
    assert result.terminated_reason == "error"
    errors = loop.history.by_type("error")
    assert any(e.content.get("context") == "monitor_action" for e in errors)


# ════════════════════════════════════════════════════════════════════
# debug=True genera RunLog
# ════════════════════════════════════════════════════════════════════

def test_debug_false_returns_log_none() -> None:
    agent = _mk_mock_agent()
    loop = InstantLoop(agent=agent, max_steps=1, debug=False)
    result = loop.run("hola")
    assert result.log is None


def test_debug_true_returns_runlog_populated() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        loop = InstantLoop(agent=agent, name="dbgtest",
                           max_steps=2, debug=True, debug_base_path=tmp)
        result = loop.run("hola")
        assert isinstance(result.log, RunLog)
        assert result.log.run_id == result.run_id
        assert result.log.sequence_num == 1
        assert len(result.log.turns) == 2
        # Verificar que escribió archivos
        loop_folder = Path(tmp) / "dbgtest"
        run_folders = list(loop_folder.iterdir())
        assert len(run_folders) == 1
        files = [f.name for f in run_folders[0].iterdir()]
        assert "config.json" in files
        assert "turn_001.json" in files
        assert "turn_002.json" in files
        assert "run_end.json" in files


def test_debug_sequence_num_increments() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        loop = InstantLoop(agent=agent, name="seq_test",
                           max_steps=1, debug=True, debug_base_path=tmp)
        r1 = loop.run("uno")
        r2 = loop.run("dos")
        r3 = loop.run("tres")
        assert r1.log.sequence_num == 1
        assert r2.log.sequence_num == 2
        assert r3.log.sequence_num == 3


# ════════════════════════════════════════════════════════════════════
# Multi-loop sobre el mismo History
# ════════════════════════════════════════════════════════════════════

def test_multi_loop_same_history() -> None:
    """Dos Loops sobre el mismo History acumulan entries con origin distinto."""
    h = History()
    a1 = _mk_mock_agent()
    a2 = _mk_mock_agent()
    loop_A = InstantLoop(agent=a1, history=h, name="A", max_steps=1)
    loop_B = InstantLoop(agent=a2, history=h, name="B", max_steps=1)
    loop_A.run("a-prompt")
    loop_B.run("b-prompt")
    starts = h.by_type("run_start")
    assert len(starts) == 2
    origins = sorted(s.content["origin"] for s in starts)
    assert origins == ["A", "B"]


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # Construcción
        ("construct_with_minimal_args",               test_construct_with_minimal_args),
        ("construct_with_existing_history",           test_construct_with_existing_history),
        ("construct_with_custom_name",                test_construct_with_custom_name),
        ("construct_rejects_negative_max_steps",      test_construct_rejects_negative_max_steps),
        ("construct_rejects_non_int_max_steps",       test_construct_rejects_non_int_max_steps),
        ("construct_max_steps_zero_allowed",          test_construct_max_steps_zero_allowed),
        ("construct_view_unknown_raises",             test_construct_view_unknown_raises),
        ("construct_auto_registers_loop_default_view", test_construct_auto_registers_loop_default_view),
        ("construct_does_not_overwrite_existing_view", test_construct_does_not_overwrite_existing_view),
        # Run básico
        ("run_returns_run_result",                    test_run_returns_run_result),
        ("run_emits_run_start_and_run_end",           test_run_emits_run_start_and_run_end),
        ("run_emits_prompt_entry",                    test_run_emits_prompt_entry),
        ("run_emits_step_start_step_end_per_step",    test_run_emits_step_start_step_end_per_step),
        ("run_bridge_appends_response_entries",       test_run_bridge_appends_response_entries),
        ("run_origin_set_on_orchestrator_entries",    test_run_origin_set_on_orchestrator_entries),
        # Stop conditions
        ("max_steps_terminates_when_no_other_stop",   test_max_steps_terminates_when_no_other_stop),
        ("max_steps_zero_means_no_cap",               test_max_steps_zero_means_no_cap),
        ("stop_signal_via_monitor",                   test_stop_signal_via_monitor),
        ("loop_stop_external",                         test_loop_stop_external),
        ("view_can_short_circuit_with_stop_reason",   test_view_can_short_circuit_with_stop_reason),
        # Sugar stop_tool
        ("stop_tool_single_name",                     test_stop_tool_single_name),
        ("stop_tool_multiple_names",                  test_stop_tool_multiple_names),
        ("stop_tool_does_not_fire_for_other_tools",   test_stop_tool_does_not_fire_for_other_tools),
        # Freshness
        ("freshness_filter_ignores_old_stop_signals", test_freshness_filter_ignores_old_stop_signals),
        ("freshness_filter_catches_signal_during_run", test_freshness_filter_catches_signal_during_run),
        # Errores
        ("agent_exception_caught_and_emits_error_entry", test_agent_exception_caught_and_emits_error_entry),
        ("monitor_action_exception_caught",           test_monitor_action_exception_caught),
        # debug
        ("debug_false_returns_log_none",              test_debug_false_returns_log_none),
        ("debug_true_returns_runlog_populated",       test_debug_true_returns_runlog_populated),
        ("debug_sequence_num_increments",             test_debug_sequence_num_increments),
        # Multi-loop
        ("multi_loop_same_history",                   test_multi_loop_same_history),
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
