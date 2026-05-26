"""
Tests transversales después del PR 7 (cross PR 2/4/5/6/7).

Verifican que los primitivos de Capa 1 del RunLog se integran
correctamente con el resto del v2:

- Bridge (PR 5) y TurnLog comparten data del mismo RunInfo.
- Snapshot config del agente (PR 6) llega al config.json de la Capa 3.
- run_params completo (PR 4) sobrevive en el TurnLog.
- reasoning_tokens (PR 4) sobrevive en TurnLog.usage.
- Multi-write/load cycle.

Sin LLM ni red.
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.debug import (
    TurnLog, write_agent_call_log, load_agent_call_logs,
)
from instantneo.history import History
from instantneo.history.from_run_info import append_entry_from_run


def _mk_run_info(*, error=None, response_content="hi"):
    return SimpleNamespace(
        error=error,
        prompt="hola",
        response_content=response_content,
        reasoning="thinking step",
        finish_reason="stop",
        usage={"input_tokens": 30, "output_tokens": 15,
               "total_tokens": 45, "reasoning_tokens": 5},  # PR 4
        duration_ms=100.0,
        provider="openai",
        model="gpt-5-mini",
        timestamp="2026-05-11T12:00:00Z",
        run_params={  # PR 4 — snapshot completo
            "model": "gpt-5-mini", "temperature": 0.7,
            "reasoning": "high", "image_detail": "low",
            "custom_thing": 42,
        },
        provider_timing=None,
        llm_calls=[SimpleNamespace(
            messages_sent=[{"role": "user"}],
            response_content=response_content,
            finish_reason="stop", tool_calls_requested=[],
            usage={"reasoning_tokens": 5}, response_id="rid_abc",
            response_model="gpt-5-mini-2026",
            reasoning_content="thinking step",
            raw_response="NOT_JSON_SAFE",
        )],
        tool_executions=[
            SimpleNamespace(name="my_tool", arguments={"k": "v"},
                            result={"ok": True}, exception=None,
                            execution_mode="wait_response"),
        ],
        messages_sent=[{"role": "user", "content": "hola"}],
    )


class _MockCapabilities:
    def get_schemas(self):
        return [{"type": "function",
                 "function": {"name": "my_tool", "description": "x",
                              "parameters": {"type": "object",
                                             "properties": {}, "required": []}}}]


def _mk_mock_agent():
    class _Agent:
        def __init__(self):
            self.last_run = _mk_run_info()
            self.config = SimpleNamespace(
                provider="openai", model="gpt-5-mini",
                api_key="sk-LEAK", role_setup="Soy un asistente.",
                temperature=0.7, max_tokens=200,
                presence_penalty=None, frequency_penalty=None,
                stop=None, seed=None, stream=False, logit_bias=None,
                images=None, image_detail="auto",
                service_account_file=None, location=None,
            )
            self.capabilities = _MockCapabilities()
        def get_resolved_role_setup(self, shelf_context=None):
            return "Soy un asistente.\n[resolved]"
    return _Agent()


# ════════════════════════════════════════════════════════════════════
# TurnLog ↔ Bridge: comparten data del mismo RunInfo
# ════════════════════════════════════════════════════════════════════

def test_turnlog_and_bridge_consume_same_runinfo() -> None:
    """Dado un mismo RunInfo, el TurnLog y el bridge producen data
    coherente entre sí (response_content, usage, etc.)."""
    ri = _mk_run_info()
    # Bridge → entries del History
    h = History()
    entries = append_entry_from_run(h, ri, turn_num=1, author="agent",
                                     origin="loop", run_id="r")
    response_entry = h.by_type("response")[0]

    # TurnLog from same RunInfo
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )

    # Mismos valores en ambos
    assert response_entry.content["text"] == tl.response_content
    assert response_entry.content["reasoning"] == tl.reasoning
    assert response_entry.content["usage"]["reasoning_tokens"] == \
           tl.usage["reasoning_tokens"] == 5
    assert response_entry.content["model"] == tl.model
    assert response_entry.content["run_params"] == tl.run_params


def test_turnlog_messages_sent_carries_more_than_response_entry() -> None:
    """El TurnLog tiene messages_sent (data pesada) que el History entry NO."""
    ri = _mk_run_info()
    h = History()
    append_entry_from_run(h, ri, turn_num=1, author="agent",
                          origin="loop", run_id="r")
    response_entry = h.by_type("response")[0]

    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )

    # History entry NO incluye messages_sent (es lean)
    assert "messages_sent" not in response_entry.content
    # TurnLog SÍ
    assert tl.messages_sent == [{"role": "user", "content": "hola"}]


# ════════════════════════════════════════════════════════════════════
# Capa 3: write_agent_call_log preserva PR 4/6 fields
# ════════════════════════════════════════════════════════════════════

def test_full_pipeline_write_load_roundtrip() -> None:
    """End-to-end: agent → write_agent_call_log → load → verificar shape."""
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "20260511_120000_call_001"
        write_agent_call_log(agent, folder, call_id="manual-001")

        loaded = load_agent_call_logs(Path(tmp))
        assert len(loaded) == 1
        cfg = loaded[0]["config"]
        call = loaded[0]["call"]

        # Snapshot del agente (PR 6)
        assert cfg["agent"]["provider"] == "openai"
        assert cfg["agent"]["role_setup_resolved"] == "Soy un asistente.\n[resolved]"
        assert len(cfg["agent"]["tools"]) == 1

        # PR 4: run_params completo
        assert call["run_params"]["reasoning"] == "high"
        assert call["run_params"]["custom_thing"] == 42

        # PR 4: reasoning_tokens en usage
        assert call["usage"]["reasoning_tokens"] == 5

        # call_id
        assert cfg["call_id"] == "manual-001"


def test_write_load_multi_call_cycle() -> None:
    """3 writes secuenciales → load devuelve 3 ordenados."""
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "my_agent"
        for ts in ["20260511_100000", "20260511_100100", "20260511_100200"]:
            folder = base / f"{ts}_call"
            write_agent_call_log(agent, folder)

        loaded = load_agent_call_logs(base)
        assert len(loaded) == 3
        # Lex order de folder names
        names = [e["folder"].name for e in loaded]
        assert names == sorted(names)


def test_config_json_no_api_key_leak_end_to_end() -> None:
    """En el pipeline completo, api_key no debe aparecer NUNCA."""
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        write_agent_call_log(agent, folder)
        all_files = list(folder.glob("*.json"))
        for f in all_files:
            content = f.read_text()
            assert "sk-LEAK" not in content
            assert "api_key" not in content


def test_extra_metadata_persisted() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        write_agent_call_log(
            agent, folder,
            extra={"experiment": "v7", "user": "tester", "n_runs": 3},
        )
        cfg = json.loads((folder / "config.json").read_text())
        assert cfg["extra"]["experiment"] == "v7"
        assert cfg["extra"]["n_runs"] == 3


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("turnlog_and_bridge_consume_same_runinfo",
         test_turnlog_and_bridge_consume_same_runinfo),
        ("turnlog_messages_sent_carries_more_than_response_entry",
         test_turnlog_messages_sent_carries_more_than_response_entry),
        ("full_pipeline_write_load_roundtrip",
         test_full_pipeline_write_load_roundtrip),
        ("write_load_multi_call_cycle",
         test_write_load_multi_call_cycle),
        ("config_json_no_api_key_leak_end_to_end",
         test_config_json_no_api_key_leak_end_to_end),
        ("extra_metadata_persisted",
         test_extra_metadata_persisted),
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
