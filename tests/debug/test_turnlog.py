"""
Tests de ``TurnLog`` (PR 7 — Capa 1 del RunLog).

Doc rector: docs/design/log-design.md líneas 137-189.

Dual-mode.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.debug import TurnLog


def _mk_run_info(
    *,
    error=None, response_content="hi", reasoning=None,
    finish_reason="stop", tool_executions=None,
    llm_calls=None, usage=None, run_params=None,
):
    if usage is None:
        usage = {"input_tokens": 5, "output_tokens": 3,
                 "total_tokens": 8, "reasoning_tokens": None}
    if run_params is None:
        run_params = {"model": "gpt-5-mini", "temperature": 0.5}
    if llm_calls is None:
        llm_calls = [SimpleNamespace(
            messages_sent=[{"role": "user", "content": "x"}],
            response_content=response_content,
            finish_reason=finish_reason,
            tool_calls_requested=[],
            usage=usage,
            response_id="rid_001",
            response_model="gpt-5-mini",
            reasoning_content=reasoning,
            raw_response="<NOT SERIALIZABLE>",
        )]
    return SimpleNamespace(
        error=error,
        prompt="hola",
        response_content=response_content,
        reasoning=reasoning,
        finish_reason=finish_reason,
        usage=usage,
        duration_ms=12.5,
        provider="openai",
        model="gpt-5-mini",
        timestamp="2026-05-11T10:00:00Z",
        run_params=run_params,
        provider_timing=None,
        llm_calls=llm_calls,
        tool_executions=tool_executions or [],
        messages_sent=[{"role": "user", "content": "hola"}],
    )


# ════════════════════════════════════════════════════════════════════
# from_runinfo — casos básicos
# ════════════════════════════════════════════════════════════════════

def test_from_runinfo_basic_response() -> None:
    ri = _mk_run_info(response_content="resp", reasoning="thinking")
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="2026-05-11T10:00:00Z",
        completed_at="2026-05-11T10:00:01Z", run_info=ri,
    )
    assert tl.step_num == 1
    assert tl.prompt == "hola"
    assert tl.response_content == "resp"
    assert tl.reasoning == "thinking"
    assert tl.provider == "openai"
    assert tl.model == "gpt-5-mini"
    assert tl.request_started_at == "2026-05-11T10:00:00Z"


def test_from_runinfo_with_error() -> None:
    ri = _mk_run_info(error="ConnectionError")
    tl = TurnLog.from_runinfo(
        step_num=2, started_at="t1", completed_at=None, run_info=ri,
    )
    assert tl.error == "ConnectionError"
    assert tl.completed_at is None
    assert tl.step_num == 2


def test_from_runinfo_with_tool_executions() -> None:
    ri = _mk_run_info(
        tool_executions=[
            SimpleNamespace(name="search", arguments={"q": "x"},
                            result={"hits": 1}, exception=None,
                            execution_mode="wait_response"),
            SimpleNamespace(name="add", arguments={"a": 1, "b": 2},
                            result=3, exception=None,
                            execution_mode="wait_response"),
        ],
    )
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )
    assert len(tl.tool_executions) == 2
    assert tl.tool_executions[0]["name"] == "search"
    assert tl.tool_executions[0]["arguments"] == {"q": "x"}
    assert tl.tool_executions[1]["result"] == 3


def test_from_runinfo_response_id_from_first_call() -> None:
    """Multi-call: response_id/model salen del primero."""
    ri = _mk_run_info(llm_calls=[
        SimpleNamespace(messages_sent=[], response_content="a",
                        finish_reason="stop", tool_calls_requested=[],
                        usage=None, response_id="FIRST",
                        response_model="model_a",
                        reasoning_content=None, raw_response=None),
        SimpleNamespace(messages_sent=[], response_content="b",
                        finish_reason="stop", tool_calls_requested=[],
                        usage=None, response_id="SECOND",
                        response_model="model_b",
                        reasoning_content=None, raw_response=None),
    ])
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )
    assert tl.response_id == "FIRST"
    assert tl.response_model == "model_a"


def test_from_runinfo_llm_calls_exclude_raw_response() -> None:
    """llm_calls serializados NO incluyen raw_response (no JSON-safe)."""
    ri = _mk_run_info()
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )
    assert len(tl.llm_calls) == 1
    assert "raw_response" not in tl.llm_calls[0]
    assert tl.llm_calls[0]["response_id"] == "rid_001"


def test_from_runinfo_image_detail_from_run_params() -> None:
    """image_detail viene del snapshot completo de run_params (PR 4)."""
    ri = _mk_run_info(run_params={"model": "x", "image_detail": "high"})
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )
    assert tl.image_detail == "high"


def test_from_runinfo_image_detail_none_when_absent() -> None:
    ri = _mk_run_info(run_params={"model": "x"})
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )
    assert tl.image_detail is None


def test_from_runinfo_images_is_none_by_default() -> None:
    """images queda en None por ahora — no derivable de RunInfo sin
    parser de messages_sent (follow-up documentado)."""
    ri = _mk_run_info()
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )
    assert tl.images is None


def test_from_runinfo_no_llm_calls_response_id_none() -> None:
    """Caso degenerado: no hay llm_calls → response_id/model = None."""
    ri = _mk_run_info(llm_calls=[])
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )
    assert tl.response_id is None
    assert tl.response_model is None


def test_from_runinfo_run_params_preserved_as_is() -> None:
    """run_params se preserva tal cual (snapshot completo del PR 4)."""
    ri = _mk_run_info(run_params={
        "model": "o4-mini",
        "reasoning": "high",
        "custom_kwarg": 42,
    })
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )
    assert tl.run_params == {
        "model": "o4-mini", "reasoning": "high", "custom_kwarg": 42,
    }


# ════════════════════════════════════════════════════════════════════
# to_dict / from_dict roundtrip
# ════════════════════════════════════════════════════════════════════

def test_to_dict_is_json_safe() -> None:
    """to_dict + json.dumps no levanta."""
    ri = _mk_run_info()
    tl = TurnLog.from_runinfo(
        step_num=1, started_at="t", completed_at="t", run_info=ri,
    )
    serialized = json.dumps(tl.to_dict(), default=str)
    assert isinstance(serialized, str)
    assert len(serialized) > 0


def test_from_dict_roundtrip() -> None:
    """to_dict → json → from_dict produce un objeto equivalente."""
    ri = _mk_run_info(reasoning="thinking", response_content="resp")
    original = TurnLog.from_runinfo(
        step_num=3, started_at="t1", completed_at="t2", run_info=ri,
    )
    js = json.dumps(original.to_dict(), default=str)
    restored = TurnLog.from_dict(json.loads(js))
    assert restored.step_num == original.step_num
    assert restored.response_content == original.response_content
    assert restored.reasoning == original.reasoning
    assert restored.usage == original.usage


def test_from_dict_tolerates_extra_keys() -> None:
    """from_dict ignora keys extra (no rompe)."""
    data = {
        "step_num": 1, "started_at": "t", "completed_at": "t",
        "prompt": "p", "images": None, "image_detail": None,
        "messages_sent": [], "run_params": {},
        "response_content": None, "reasoning": None,
        "finish_reason": None, "usage": None,
        "llm_calls": [], "tool_executions": [],
        "provider": "x", "model": "y", "response_id": None,
        "response_model": None, "duration_ms": None,
        "provider_timing": None, "request_started_at": "t",
        "error": None,
        "extra_unknown_key": "ignored",
    }
    tl = TurnLog.from_dict(data)
    assert tl.step_num == 1


def test_from_dict_tolerates_missing_keys() -> None:
    """from_dict rellena defaults para keys faltantes."""
    tl = TurnLog.from_dict({"step_num": 5})
    assert tl.step_num == 5
    assert tl.prompt == ""
    assert tl.messages_sent == []
    assert tl.run_params == {}


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("from_runinfo_basic_response",          test_from_runinfo_basic_response),
        ("from_runinfo_with_error",              test_from_runinfo_with_error),
        ("from_runinfo_with_tool_executions",    test_from_runinfo_with_tool_executions),
        ("from_runinfo_response_id_from_first_call", test_from_runinfo_response_id_from_first_call),
        ("from_runinfo_llm_calls_exclude_raw_response", test_from_runinfo_llm_calls_exclude_raw_response),
        ("from_runinfo_image_detail_from_run_params", test_from_runinfo_image_detail_from_run_params),
        ("from_runinfo_image_detail_none_when_absent", test_from_runinfo_image_detail_none_when_absent),
        ("from_runinfo_images_is_none_by_default", test_from_runinfo_images_is_none_by_default),
        ("from_runinfo_no_llm_calls_response_id_none", test_from_runinfo_no_llm_calls_response_id_none),
        ("from_runinfo_run_params_preserved_as_is", test_from_runinfo_run_params_preserved_as_is),
        ("to_dict_is_json_safe",                 test_to_dict_is_json_safe),
        ("from_dict_roundtrip",                  test_from_dict_roundtrip),
        ("from_dict_tolerates_extra_keys",       test_from_dict_tolerates_extra_keys),
        ("from_dict_tolerates_missing_keys",     test_from_dict_tolerates_missing_keys),
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
