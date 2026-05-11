"""
Tests transversales después del PR 8 (cross PR 2/3/4/5/6/7/8).

El Loop integra todo el v2. Estos tests verifican el comportamiento
end-to-end con agente mockeado:

- Pipeline completo: agent.run → bridge → History → Monitor → stop.
- run_start contiene snapshot del agente (PR 6).
- TurnLog del debug RunLog contiene reasoning_tokens (PR 4).
- Vista loop_default consume entries del bridge correctamente.
- current_run_config refleja el run actual (queries PR 5).
- Multi-run sobre el mismo History.

Sin LLM ni red — agente mockeado.
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.history.queries import current_run_config, current_run_id
from instantneo.loop import InstantLoop, RunResult, RenderedPrompt, RunLog
from instantneo.monitor import Monitor
from instantneo.monitor.conditions import when_type_present, when_last_tool_called
from instantneo.monitor.actions import stop_signal


class _MockCaps:
    def __init__(self, schemas=None):
        self._schemas = schemas or [{
            "type": "function",
            "function": {"name": "search", "description": "search the web",
                         "parameters": {"type": "object", "properties": {}, "required": []}},
        }]
    def get_schemas(self):
        return list(self._schemas)


def _mk_agent_factory(*, response_factory=None, schemas=None):
    """Crea un mock de InstantNeo configurable."""
    class _Agent:
        def __init__(self):
            self.config = SimpleNamespace(
                provider="mock", model="mock-m",
                api_key="sk-MOCK", role_setup="Sos un asistente.",
                temperature=0.7, max_tokens=200,
                presence_penalty=None, frequency_penalty=None,
                stop=None, seed=None, stream=False, logit_bias=None,
                images=None, image_detail="auto",
                location=None, service_account_file=None,
            )
            self.capabilities = _MockCaps(schemas)
            self.last_run = None
            self._count = 0
        def get_resolved_role_setup(self, shelf_context=None):
            base = "Sos un asistente. [resolved]"
            return f"{base}\n+ {shelf_context}" if shelf_context else base
        def run(self, prompt, images=None, image_detail=None):
            self._count += 1
            if response_factory:
                self.last_run = response_factory(prompt, self._count)
            else:
                self.last_run = SimpleNamespace(
                    error=None, prompt=prompt,
                    response_content=f"resp #{self._count}",
                    reasoning="thinking",
                    finish_reason="stop",
                    usage={"input_tokens": 10, "output_tokens": 5,
                           "total_tokens": 15, "reasoning_tokens": 3},
                    duration_ms=20.0,
                    provider="mock", model="mock-m",
                    timestamp="2026-05-11T10:00:00Z",
                    run_params={"model": "mock-m", "reasoning": "high",
                                "image_detail": "auto"},
                    provider_timing=None,
                    llm_calls=[SimpleNamespace(
                        messages_sent=[], response_content="r",
                        finish_reason="stop", tool_calls_requested=[],
                        usage=None, response_id="rid", response_model="m",
                        reasoning_content="thinking", raw_response=None,
                    )],
                    tool_executions=[],
                    messages_sent=[],
                )
    return _Agent


# ════════════════════════════════════════════════════════════════════
# run_start contiene snapshot del agente (cross PR 6 + PR 8)
# ════════════════════════════════════════════════════════════════════

def test_run_start_includes_agent_snapshot() -> None:
    Agent = _mk_agent_factory()
    loop = InstantLoop(agent=Agent(), name="t", max_steps=1)
    loop.run("hola")
    rs = loop.history.by_type("run_start")[0]
    agent_section = rs.content["agent"]
    assert agent_section["provider"] == "mock"
    assert agent_section["model"] == "mock-m"
    assert "role_setup_resolved" in agent_section
    assert "tools" in agent_section
    assert len(agent_section["tools"]) == 1
    # NO api_key leak
    assert "sk-MOCK" not in json.dumps(rs.content)


def test_run_start_includes_loop_metadata() -> None:
    Agent = _mk_agent_factory()
    loop = InstantLoop(
        agent=Agent(), name="meta", max_steps=42,
        stop_signals=["x"], stop_tool="finalizar", debug=False,
    )
    loop.run("hola")
    rs = loop.history.by_type("run_start")[0]
    loop_section = rs.content["loop"]
    assert loop_section["name"] == "meta"
    assert loop_section["max_steps"] == 42
    # stop_signals incluye el auto del sugar stop_tool
    assert "agent called finalizar" in loop_section["stop_signals"]
    assert loop_section["stop_tool"] == ["finalizar"]
    assert loop_section["debug"] is False


# ════════════════════════════════════════════════════════════════════
# Bridge + Loop: entries operacionales + narrativas convivem
# ════════════════════════════════════════════════════════════════════

def test_full_step_emits_expected_entry_types() -> None:
    Agent = _mk_agent_factory()
    loop = InstantLoop(agent=Agent(), name="t", max_steps=1)
    loop.run("hola")
    types_observed = [e.type for e in loop.history.all()]
    # Esperado por step (1 step): run_start, prompt, step_start, response,
    # step_end, run_end. (Sin tool_calls, sin stop_signal.)
    for expected in ["run_start", "prompt", "step_start", "response", "step_end", "run_end"]:
        assert expected in types_observed, f"falta {expected}"


def test_response_entry_has_reasoning_tokens_from_pr4() -> None:
    Agent = _mk_agent_factory()
    loop = InstantLoop(agent=Agent(), name="t", max_steps=1)
    loop.run("hola")
    resp = loop.history.by_type("response")[0]
    # PR 4 propagó reasoning_tokens; el bridge lo guardó en content.usage
    assert resp.content["usage"]["reasoning_tokens"] == 3


def test_response_entry_has_run_params_snapshot_from_pr4() -> None:
    Agent = _mk_agent_factory()
    loop = InstantLoop(agent=Agent(), name="t", max_steps=1)
    loop.run("hola")
    resp = loop.history.by_type("response")[0]
    rp = resp.content["run_params"]
    assert rp["reasoning"] == "high"
    assert rp["image_detail"] == "auto"


# ════════════════════════════════════════════════════════════════════
# Queries del PR 5 funcionan post-pipeline
# ════════════════════════════════════════════════════════════════════

def test_current_run_config_reflects_active_run() -> None:
    Agent = _mk_agent_factory()
    loop = InstantLoop(agent=Agent(), name="qtest", max_steps=1)
    result = loop.run("hola")
    cfg = current_run_config(loop.history)
    assert cfg is not None
    assert cfg["origin"] == "qtest"
    assert cfg["run_id"] == result.run_id


def test_current_run_id_matches_result_run_id() -> None:
    Agent = _mk_agent_factory()
    loop = InstantLoop(agent=Agent(), name="t", max_steps=1)
    result = loop.run("hola")
    assert current_run_id(loop.history) == result.run_id


# ════════════════════════════════════════════════════════════════════
# Vista loop_default consume bien las entries del Loop
# ════════════════════════════════════════════════════════════════════

def test_view_renders_user_prompt_and_response() -> None:
    Agent = _mk_agent_factory()
    loop = InstantLoop(agent=Agent(), name="t", max_steps=2)
    # Inspeccionar lo que la vista produciría al inicio del step 2
    loop.run("query inicial")
    # Después del run, podemos exportar la vista para ver el último estado
    rendered = loop.history.export("loop_default")
    assert isinstance(rendered, RenderedPrompt)
    text = rendered.text
    assert "query inicial" in text
    assert "resp #1" in text
    assert "resp #2" in text


# ════════════════════════════════════════════════════════════════════
# Sugar stop_tool con bridge real
# ════════════════════════════════════════════════════════════════════

def test_sugar_stop_tool_with_real_bridge() -> None:
    """El agente llama 'finalizar' → el bridge lo registra → el sugar
    monitor lo detecta → emite stop_signal → loop rompe."""
    def factory(prompt, count):
        return SimpleNamespace(
            error=None, prompt=prompt,
            response_content=None,
            reasoning=None, finish_reason="tool_calls",
            usage=None, duration_ms=10.0,
            provider="mock", model="m",
            timestamp="t", run_params={},
            provider_timing=None,
            llm_calls=[SimpleNamespace(
                messages_sent=[], response_content=None,
                finish_reason="tool_calls", tool_calls_requested=[],
                usage=None, response_id="rid", response_model="m",
                reasoning_content=None, raw_response=None,
            )],
            tool_executions=[SimpleNamespace(
                name="finalizar", arguments={"summary": "listo"},
                result={"summary": "listo"}, exception=None,
                execution_mode="wait_response",
            )],
            messages_sent=[],
        )
    Agent = _mk_agent_factory(response_factory=factory)
    loop = InstantLoop(agent=Agent(), name="sugar_test",
                       stop_tool="finalizar", max_steps=10)
    result = loop.run("trabajá hasta finalizar")
    assert result.terminated_reason == "stop_signal"
    assert result.stop_reason == "agent called finalizar"
    assert result.total_steps == 1


# ════════════════════════════════════════════════════════════════════
# debug=True genera RunLog completo
# ════════════════════════════════════════════════════════════════════

def test_debug_runlog_includes_turns_with_full_shape() -> None:
    Agent = _mk_agent_factory()
    with tempfile.TemporaryDirectory() as tmp:
        loop = InstantLoop(agent=Agent(), name="dbg", max_steps=2,
                           debug=True, debug_base_path=tmp)
        result = loop.run("hola")
        assert result.log is not None
        assert len(result.log.turns) == 2
        # Cada turn tiene reasoning_tokens del PR 4
        for t in result.log.turns:
            assert t.usage["reasoning_tokens"] == 3
            assert t.run_params["reasoning"] == "high"


def test_debug_runlog_config_has_agent_and_loop_sections() -> None:
    Agent = _mk_agent_factory()
    with tempfile.TemporaryDirectory() as tmp:
        loop = InstantLoop(agent=Agent(), name="dbg_cfg", max_steps=1,
                           debug=True, debug_base_path=tmp)
        loop.run("hola")
        loop_folder = Path(tmp) / "dbg_cfg"
        run_folder = list(loop_folder.iterdir())[0]
        cfg = json.loads((run_folder / "config.json").read_text())
        assert "agent" in cfg
        assert "loop" in cfg
        assert "input" in cfg
        # input incluye el prompt original
        assert cfg["input"]["prompt"] == "hola"
        # NO leak api_key
        assert "sk-MOCK" not in json.dumps(cfg)


# ════════════════════════════════════════════════════════════════════
# Multi-run sobre mismo History (PR 2 + PR 8)
# ════════════════════════════════════════════════════════════════════

def test_multi_run_same_history_accumulates() -> None:
    Agent = _mk_agent_factory()
    h = History()
    loop = InstantLoop(agent=Agent(), history=h, name="multi", max_steps=1)
    r1 = loop.run("primer prompt")
    r2 = loop.run("segundo prompt")
    r3 = loop.run("tercer prompt")
    # 3 run_starts, 3 run_ends, 3 prompts
    assert len(h.by_type("run_start")) == 3
    assert len(h.by_type("run_end")) == 3
    assert len(h.by_type("prompt")) == 3
    # Cada run tiene su run_id único
    run_ids = {r1.run_id, r2.run_id, r3.run_id}
    assert len(run_ids) == 3


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("run_start_includes_agent_snapshot",         test_run_start_includes_agent_snapshot),
        ("run_start_includes_loop_metadata",          test_run_start_includes_loop_metadata),
        ("full_step_emits_expected_entry_types",      test_full_step_emits_expected_entry_types),
        ("response_entry_has_reasoning_tokens_from_pr4", test_response_entry_has_reasoning_tokens_from_pr4),
        ("response_entry_has_run_params_snapshot_from_pr4", test_response_entry_has_run_params_snapshot_from_pr4),
        ("current_run_config_reflects_active_run",    test_current_run_config_reflects_active_run),
        ("current_run_id_matches_result_run_id",      test_current_run_id_matches_result_run_id),
        ("view_renders_user_prompt_and_response",     test_view_renders_user_prompt_and_response),
        ("sugar_stop_tool_with_real_bridge",          test_sugar_stop_tool_with_real_bridge),
        ("debug_runlog_includes_turns_with_full_shape", test_debug_runlog_includes_turns_with_full_shape),
        ("debug_runlog_config_has_agent_and_loop_sections", test_debug_runlog_config_has_agent_and_loop_sections),
        ("multi_run_same_history_accumulates",        test_multi_run_same_history_accumulates),
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
