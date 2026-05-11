"""
Tests del bridge ``append_entry_from_run`` (PR 5).

Doc rector: docs/design/runinfo-to-entries.md sección "Función
append_entry_from_run" (líneas 23-115) y "Decisiones del shape de cada
entry" (líneas 126-191).

Cada test construye un ``RunInfo`` sintético (vía SimpleNamespace) y
verifica el shape exacto de las entries generadas. No requiere LLM
ni red.

Dual-mode.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.history.from_run_info import append_entry_from_run


# ────────────────────────────────────────────────────────────────────
# Fixture helper: construye RunInfo sintético configurable
# ────────────────────────────────────────────────────────────────────

def _mk_run_info(
    *,
    response_content="hola",
    reasoning=None,
    finish_reason="stop",
    usage=None,
    duration_ms=100.0,
    provider="openai",
    model="gpt-4o-mini",
    timestamp="2026-05-11T12:00:00Z",
    run_params=None,
    provider_timing=None,
    llm_calls=None,
    tool_executions=None,
    error=None,
):
    """Construye un RunInfo sintético — todos los campos con defaults razonables."""
    if usage is None:
        usage = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30,
                 "reasoning_tokens": None}
    if run_params is None:
        run_params = {"model": model, "temperature": 0.7}
    if llm_calls is None:
        llm_calls = [SimpleNamespace(response_id="resp_001", response_model=model)]
    return SimpleNamespace(
        error=error,
        response_content=response_content,
        reasoning=reasoning,
        finish_reason=finish_reason,
        usage=usage,
        duration_ms=duration_ms,
        provider=provider,
        model=model,
        timestamp=timestamp,
        run_params=run_params,
        provider_timing=provider_timing,
        llm_calls=llm_calls,
        tool_executions=tool_executions or [],
    )


def _mk_tool_exec(
    name="my_tool", arguments=None, result=None,
    exception=None, execution_mode="wait_response",
):
    return SimpleNamespace(
        name=name,
        arguments=arguments if arguments is not None else {"k": "v"},
        result=result if result is not None else "ok",
        exception=exception,
        execution_mode=execution_mode,
    )


# ════════════════════════════════════════════════════════════════════
# Caso 1: response only
# ════════════════════════════════════════════════════════════════════

def test_response_only_emits_single_response_entry() -> None:
    """RunInfo con response, sin tools → 1 entry tipo response."""
    h = History()
    ri = _mk_run_info()
    entries = append_entry_from_run(
        h, ri, turn_num=1, author="A", origin="loop_t", run_id="r1",
    )
    assert len(entries) == 1
    assert entries[0].type == "response"
    assert entries[0].author == "A"
    assert entries[0].content["text"] == "hola"


def test_response_content_has_all_expected_keys() -> None:
    """response.content tiene los 15 campos del shape canónico."""
    h = History()
    ri = _mk_run_info()
    entries = append_entry_from_run(
        h, ri, turn_num=1, author="A", origin="o", run_id="r",
    )
    expected = {
        "text", "reasoning", "finish_reason", "usage", "duration_ms",
        "provider", "model", "response_id", "response_model",
        "provider_timing", "request_started_at", "run_params",
        "origin", "run_id", "turn_num",
    }
    assert set(entries[0].content.keys()) == expected


# ════════════════════════════════════════════════════════════════════
# Caso 2: response + tools
# ════════════════════════════════════════════════════════════════════

def test_response_with_tools_emits_response_plus_tool_calls() -> None:
    """RunInfo con response y N tool_executions → 1 response + N tool_call."""
    h = History()
    ri = _mk_run_info(
        tool_executions=[
            _mk_tool_exec(name="a"),
            _mk_tool_exec(name="b"),
            _mk_tool_exec(name="c"),
        ],
    )
    entries = append_entry_from_run(
        h, ri, turn_num=2, author="A", origin="o", run_id="r",
    )
    assert len(entries) == 4
    types = [e.type for e in entries]
    assert types == ["response", "tool_call", "tool_call", "tool_call"]
    names = [e.content["name"] for e in entries[1:]]
    assert names == ["a", "b", "c"]


def test_only_tools_no_response_content() -> None:
    """response_content=None → solo emite tool_calls (no entry response)."""
    h = History()
    ri = _mk_run_info(
        response_content=None,
        tool_executions=[_mk_tool_exec(name="solo")],
    )
    entries = append_entry_from_run(
        h, ri, turn_num=1, author="A", origin="o", run_id="r",
    )
    assert len(entries) == 1
    assert entries[0].type == "tool_call"
    assert entries[0].content["name"] == "solo"


# ════════════════════════════════════════════════════════════════════
# Caso 3: run-level error (short-circuit)
# ════════════════════════════════════════════════════════════════════

def test_run_error_emits_only_error_entry() -> None:
    """run_info.error populado → SOLO entry error, no response ni tools."""
    h = History()
    ri = _mk_run_info(
        error="ConnectionError: timeout",
        tool_executions=[_mk_tool_exec()],  # estos NO deberían emitirse
    )
    entries = append_entry_from_run(
        h, ri, turn_num=3, author="A", origin="o", run_id="r",
    )
    assert len(entries) == 1
    assert entries[0].type == "error"
    assert entries[0].content["exception"] == "ConnectionError: timeout"
    assert entries[0].content["origin"] == "o"
    assert entries[0].content["run_id"] == "r"
    assert entries[0].content["turn_num"] == 3


def test_error_entry_content_shape() -> None:
    """error.content tiene los 7 campos esperados del doc (líneas 179-188)."""
    h = History()
    ri = _mk_run_info(error="oops")
    entries = append_entry_from_run(
        h, ri, turn_num=1, author="A", origin="o", run_id="r",
    )
    expected = {"exception", "duration_ms", "provider", "model",
                "origin", "run_id", "turn_num"}
    assert set(entries[0].content.keys()) == expected


# ════════════════════════════════════════════════════════════════════
# Tool-level exception (no short-circuit)
# ════════════════════════════════════════════════════════════════════

def test_tool_exception_does_not_short_circuit() -> None:
    """Una tool con exception preserva exception, pero el run sobrevive
    y la response y las otras tools se emiten."""
    h = History()
    ri = _mk_run_info(
        tool_executions=[
            _mk_tool_exec(name="ok_one", exception=None),
            _mk_tool_exec(name="failed", exception="ValueError: x"),
            _mk_tool_exec(name="ok_two", exception=None),
        ],
    )
    entries = append_entry_from_run(
        h, ri, turn_num=1, author="A", origin="o", run_id="r",
    )
    assert len(entries) == 4  # response + 3 tool_calls
    failed_entries = [e for e in entries if e.type == "tool_call" and e.content["exception"]]
    assert len(failed_entries) == 1
    assert failed_entries[0].content["name"] == "failed"
    assert failed_entries[0].content["exception"] == "ValueError: x"


# ════════════════════════════════════════════════════════════════════
# Preservación de tipos en arguments y result
# ════════════════════════════════════════════════════════════════════

def test_arguments_kept_as_dict_not_string() -> None:
    """arguments queda como dict en content, NO stringificado."""
    h = History()
    args = {"query": "instantneo", "limit": 5, "flag": True}
    ri = _mk_run_info(
        tool_executions=[_mk_tool_exec(arguments=args)],
    )
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    tc = entries[1]
    assert isinstance(tc.content["arguments"], dict)
    assert tc.content["arguments"] == args


def test_result_kept_native_not_str() -> None:
    """result queda con tipo nativo (dict/list/etc), no str()."""
    h = History()
    result = {"hits": [{"id": 1, "title": "x"}], "total": 1}
    ri = _mk_run_info(
        tool_executions=[_mk_tool_exec(result=result)],
    )
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    tc = entries[1]
    assert isinstance(tc.content["result"], dict)
    assert tc.content["result"] == result


def test_tool_call_content_shape() -> None:
    """tool_call.content tiene los 8 campos del doc (líneas 160-170)."""
    h = History()
    ri = _mk_run_info(tool_executions=[_mk_tool_exec()])
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    tc = entries[1]
    expected = {"name", "arguments", "result", "exception", "execution_mode",
                "origin", "run_id", "turn_num"}
    assert set(tc.content.keys()) == expected


# ════════════════════════════════════════════════════════════════════
# reasoning y reasoning_tokens
# ════════════════════════════════════════════════════════════════════

def test_reasoning_in_response_content() -> None:
    """reasoning entra como campo separado en response.content."""
    h = History()
    ri = _mk_run_info(reasoning="thinking step by step about the problem")
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    assert entries[0].content["reasoning"] == "thinking step by step about the problem"


def test_reasoning_tokens_in_usage() -> None:
    """usage.reasoning_tokens (PR 4) se preserva intacto."""
    h = History()
    usage = {"input_tokens": 50, "output_tokens": 25, "total_tokens": 75, "reasoning_tokens": 18}
    ri = _mk_run_info(usage=usage)
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    assert entries[0].content["usage"]["reasoning_tokens"] == 18


# ════════════════════════════════════════════════════════════════════
# response_id / response_model del PRIMER LLMCall
# ════════════════════════════════════════════════════════════════════

def test_response_id_and_model_from_first_llm_call() -> None:
    """Cuando hay multi-call, response_id/model salen del primero."""
    h = History()
    ri = _mk_run_info(llm_calls=[
        SimpleNamespace(response_id="first", response_model="model_a"),
        SimpleNamespace(response_id="second", response_model="model_b"),
    ])
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    assert entries[0].content["response_id"] == "first"
    assert entries[0].content["response_model"] == "model_a"


def test_response_id_and_model_none_when_no_llm_calls() -> None:
    """Si llm_calls está vacío, response_id/model quedan en None (caso degenerado)."""
    h = History()
    ri = _mk_run_info(llm_calls=[])
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    assert entries[0].content["response_id"] is None
    assert entries[0].content["response_model"] is None


# ════════════════════════════════════════════════════════════════════
# origin / run_id / turn_num en cada entry
# ════════════════════════════════════════════════════════════════════

def test_origin_run_id_turn_num_in_every_entry() -> None:
    """TODAS las entries generadas llevan origin, run_id, turn_num en content."""
    h = History()
    ri = _mk_run_info(
        tool_executions=[_mk_tool_exec(name="a"), _mk_tool_exec(name="b")],
    )
    entries = append_entry_from_run(
        h, ri, turn_num=7, author="A", origin="my_loop", run_id="run-XYZ",
    )
    for e in entries:
        assert e.content["origin"] == "my_loop"
        assert e.content["run_id"] == "run-XYZ"
        assert e.content["turn_num"] == 7


def test_origin_run_id_turn_num_in_error_entry() -> None:
    """Idem para el caso error."""
    h = History()
    ri = _mk_run_info(error="boom")
    entries = append_entry_from_run(
        h, ri, turn_num=42, author="A", origin="my_loop", run_id="run-ABC",
    )
    assert entries[0].content["origin"] == "my_loop"
    assert entries[0].content["run_id"] == "run-ABC"
    assert entries[0].content["turn_num"] == 42


# ════════════════════════════════════════════════════════════════════
# Return value y orden
# ════════════════════════════════════════════════════════════════════

def test_returns_appended_entries_in_order() -> None:
    """El return value es exactamente la lista en orden de aparición en history.all()."""
    h = History()
    ri = _mk_run_info(
        tool_executions=[_mk_tool_exec(name=f"t{i}") for i in range(3)],
    )
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    assert entries == h.all()


def test_run_params_snapshot_preserved() -> None:
    """run_info.run_params (post-PR4 = snapshot completo) se preserva en content."""
    h = History()
    run_params = {
        "model": "gpt-4o", "temperature": 0.7,
        "reasoning": "high", "image_detail": "low", "my_custom_kwarg": 42,
    }
    ri = _mk_run_info(run_params=run_params)
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    assert entries[0].content["run_params"] == run_params


def test_run_params_defaults_to_empty_dict_when_missing() -> None:
    """run_info.run_params = None → content['run_params'] = {} (no None).

    Construye el RunInfo manualmente (sin pasar por el fixture, que
    rellena defaults) para forzar run_params=None real."""
    h = History()
    ri = _mk_run_info()
    ri.run_params = None  # forzar None explícito
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    assert entries[0].content["run_params"] == {}


def test_request_started_at_from_run_info_timestamp() -> None:
    """run_info.timestamp mapea a content.request_started_at (renombrado)."""
    h = History()
    ri = _mk_run_info(timestamp="2026-05-11T10:30:00Z")
    entries = append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    assert entries[0].content["request_started_at"] == "2026-05-11T10:30:00Z"


# ════════════════════════════════════════════════════════════════════
# Bridge no toca el RunInfo
# ════════════════════════════════════════════════════════════════════

def test_bridge_does_not_mutate_run_info() -> None:
    """append_entry_from_run no muta el RunInfo recibido."""
    h = History()
    ri = _mk_run_info(reasoning="hint",
                      tool_executions=[_mk_tool_exec(name="t")])
    # Snapshot of state before
    before_response = ri.response_content
    before_reasoning = ri.reasoning
    before_tools = list(ri.tool_executions)
    append_entry_from_run(h, ri, turn_num=1, author="A", origin="o", run_id="r")
    assert ri.response_content == before_response
    assert ri.reasoning == before_reasoning
    assert list(ri.tool_executions) == before_tools


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("response_only_emits_single_response_entry", test_response_only_emits_single_response_entry),
        ("response_content_has_all_expected_keys",    test_response_content_has_all_expected_keys),
        ("response_with_tools_emits_response_plus_tool_calls", test_response_with_tools_emits_response_plus_tool_calls),
        ("only_tools_no_response_content",            test_only_tools_no_response_content),
        ("run_error_emits_only_error_entry",          test_run_error_emits_only_error_entry),
        ("error_entry_content_shape",                 test_error_entry_content_shape),
        ("tool_exception_does_not_short_circuit",     test_tool_exception_does_not_short_circuit),
        ("arguments_kept_as_dict_not_string",         test_arguments_kept_as_dict_not_string),
        ("result_kept_native_not_str",                test_result_kept_native_not_str),
        ("tool_call_content_shape",                   test_tool_call_content_shape),
        ("reasoning_in_response_content",             test_reasoning_in_response_content),
        ("reasoning_tokens_in_usage",                 test_reasoning_tokens_in_usage),
        ("response_id_and_model_from_first_llm_call", test_response_id_and_model_from_first_llm_call),
        ("response_id_and_model_none_when_no_llm_calls", test_response_id_and_model_none_when_no_llm_calls),
        ("origin_run_id_turn_num_in_every_entry",     test_origin_run_id_turn_num_in_every_entry),
        ("origin_run_id_turn_num_in_error_entry",     test_origin_run_id_turn_num_in_error_entry),
        ("returns_appended_entries_in_order",         test_returns_appended_entries_in_order),
        ("run_params_snapshot_preserved",             test_run_params_snapshot_preserved),
        ("run_params_defaults_to_empty_dict_when_missing", test_run_params_defaults_to_empty_dict_when_missing),
        ("request_started_at_from_run_info_timestamp", test_request_started_at_from_run_info_timestamp),
        ("bridge_does_not_mutate_run_info",           test_bridge_does_not_mutate_run_info),
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
