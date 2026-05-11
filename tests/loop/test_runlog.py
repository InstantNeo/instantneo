"""
Tests de ``RunLog`` Capa 2 (PR 8) en ``instantneo/loop/debug.py``.

Cubre: dataclass, append_turn con persistencia incremental,
write_config / write_run_end / write_full, load_folder roundtrip,
load_run_logs, naming del folder.
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.debug import TurnLog
from instantneo.loop.debug import (
    RunLog, load_run_logs, _new_run_log_for_loop, _compute_run_folder,
)


def _mk_turn(step_num=1):
    """Mini TurnLog construido directo (no via from_runinfo)."""
    return TurnLog(
        step_num=step_num,
        started_at="2026-05-11T10:00:00Z",
        completed_at="2026-05-11T10:00:01Z",
        prompt="p", images=None, image_detail=None,
        messages_sent=[], run_params={"model": "m"},
        response_content="r", reasoning=None,
        finish_reason="stop", usage=None,
        llm_calls=[], tool_executions=[],
        provider="mock", model="m",
        response_id=None, response_model=None,
        duration_ms=10.0, provider_timing=None,
        request_started_at="2026-05-11T10:00:00Z", error=None,
    )


# ════════════════════════════════════════════════════════════════════
# Construcción
# ════════════════════════════════════════════════════════════════════

def test_runlog_in_memory_no_output_path() -> None:
    log = RunLog(
        log_id="L1", run_id="R1", loop_name="my_loop",
        sequence_num=1, started_at="t",
    )
    assert log.turns == []
    assert log.output_path is None
    assert log.config == {}


def test_append_turn_in_memory() -> None:
    log = RunLog(log_id="L", run_id="R", loop_name="L", sequence_num=1,
                 started_at="t")
    t1 = _mk_turn(1)
    t2 = _mk_turn(2)
    log.append_turn(t1)
    log.append_turn(t2)
    assert len(log.turns) == 2
    assert log.turns[0].step_num == 1
    assert log.turns[1].step_num == 2


# ════════════════════════════════════════════════════════════════════
# Persistencia con output_path
# ════════════════════════════════════════════════════════════════════

def test_append_turn_with_output_path_writes_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "test_run"
        folder.mkdir()
        log = RunLog(log_id="L", run_id="R", loop_name="L", sequence_num=1,
                     started_at="t", output_path=folder)
        log.append_turn(_mk_turn(1))
        log.append_turn(_mk_turn(2))
        # turn_001.json y turn_002.json existen
        assert (folder / "turn_001.json").exists()
        assert (folder / "turn_002.json").exists()


def test_write_config_creates_config_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "run"
        folder.mkdir()
        log = RunLog(log_id="L1", run_id="R1", loop_name="my_loop",
                     sequence_num=2, started_at="2026-05-11T10:00:00Z",
                     config={"agent": {"provider": "mock"}, "loop": {"name": "x"}},
                     output_path=folder)
        log.write_config()
        cfg = json.loads((folder / "config.json").read_text())
        assert cfg["log_id"] == "L1"
        assert cfg["run_id"] == "R1"
        assert cfg["loop_name"] == "my_loop"
        assert cfg["sequence_num"] == 2
        assert cfg["agent"]["provider"] == "mock"


def test_write_run_end_creates_run_end_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "run"
        folder.mkdir()
        log = RunLog(log_id="L", run_id="R", loop_name="L", sequence_num=1,
                     started_at="2026-05-11T10:00:00Z",
                     completed_at="2026-05-11T10:00:05Z",
                     terminated_reason="stop_signal",
                     stop_reason="done",
                     output_path=folder)
        log.append_turn(_mk_turn(1))
        log.write_run_end()
        re_data = json.loads((folder / "run_end.json").read_text())
        assert re_data["terminated_reason"] == "stop_signal"
        assert re_data["stop_reason"] == "done"
        assert re_data["total_steps"] == 1
        # duration calculada
        assert re_data["duration_s"] == 5.0


def test_write_config_no_op_when_no_output_path() -> None:
    """Sin output_path, write_config no debe crashear."""
    log = RunLog(log_id="L", run_id="R", loop_name="L", sequence_num=1,
                 started_at="t")
    log.write_config()  # no-op


def test_write_full_writes_complete_log() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "full"
        log = RunLog(log_id="L", run_id="R", loop_name="L", sequence_num=1,
                     started_at="2026-05-11T10:00:00Z",
                     completed_at="2026-05-11T10:00:05Z",
                     terminated_reason="max_steps",
                     config={"loop": {"name": "L"}})
        log.append_turn(_mk_turn(1))
        log.append_turn(_mk_turn(2))
        log.write_full(folder)
        assert (folder / "config.json").exists()
        assert (folder / "turn_001.json").exists()
        assert (folder / "turn_002.json").exists()
        assert (folder / "run_end.json").exists()


def test_write_full_raises_if_no_path() -> None:
    log = RunLog(log_id="L", run_id="R", loop_name="L", sequence_num=1,
                 started_at="t")
    try:
        log.write_full()
    except ValueError:
        return
    raise AssertionError("Esperaba ValueError")


# ════════════════════════════════════════════════════════════════════
# Roundtrip
# ════════════════════════════════════════════════════════════════════

def test_to_dict_includes_turns_serialized() -> None:
    log = RunLog(log_id="L", run_id="R", loop_name="L", sequence_num=1,
                 started_at="t")
    log.append_turn(_mk_turn(1))
    d = log.to_dict()
    assert d["log_id"] == "L"
    assert len(d["turns"]) == 1
    assert d["turns"][0]["step_num"] == 1


def test_from_dict_roundtrip() -> None:
    original = RunLog(log_id="L1", run_id="R1", loop_name="L1", sequence_num=3,
                      started_at="t1", completed_at="t2",
                      terminated_reason="max_steps")
    original.append_turn(_mk_turn(1))
    d = original.to_dict()
    restored = RunLog.from_dict(d)
    assert restored.log_id == "L1"
    assert restored.run_id == "R1"
    assert restored.sequence_num == 3
    assert restored.terminated_reason == "max_steps"
    assert len(restored.turns) == 1
    assert restored.turns[0].step_num == 1


def test_load_folder_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "rt_test"
        original = RunLog(log_id="L", run_id="R", loop_name="L", sequence_num=5,
                          started_at="2026-05-11T10:00:00Z",
                          completed_at="2026-05-11T10:00:10Z",
                          terminated_reason="stop_signal",
                          stop_reason="done",
                          config={"loop": {"name": "L"}})
        original.append_turn(_mk_turn(1))
        original.append_turn(_mk_turn(2))
        original.write_full(folder)

        loaded = RunLog.load_folder(folder)
        assert loaded.log_id == "L"
        assert loaded.sequence_num == 5
        assert loaded.terminated_reason == "stop_signal"
        assert loaded.stop_reason == "done"
        assert len(loaded.turns) == 2


# ════════════════════════════════════════════════════════════════════
# _compute_run_folder y _new_run_log_for_loop
# ════════════════════════════════════════════════════════════════════

def test_compute_run_folder_naming() -> None:
    p = _compute_run_folder(
        Path("/tmp/dbg"), "my_loop",
        "2026-05-11T10:00:00+00:00",
        1, "abcdef1234",
    )
    assert "my_loop" in str(p)
    assert "20260511_100000" in str(p)
    assert "run_001" in str(p)
    assert "abcdef" in str(p)


def test_compute_run_folder_sanitizes_loop_name() -> None:
    """Loop name con caracteres no-safe se convierte a underscores."""
    p = _compute_run_folder(
        Path("/tmp"), "my/loop:with bad chars",
        "2026-05-11T10:00:00+00:00",
        1, "abcdef",
    )
    assert "/" not in p.parts[-2] or p.parts[-2] == "tmp"  # parts intermedios pueden tener /
    # El loop name sanitized no tiene caracteres especiales
    loop_segment = p.parts[-2]
    assert ":" not in loop_segment
    assert " " not in loop_segment


def test_new_run_log_for_loop_in_memory() -> None:
    """Sin base_path, output_path queda en None."""
    log = _new_run_log_for_loop(
        loop_name="L", sequence_num=1, run_id="rid",
        started_at_iso="t", config={"loop": {}},
        base_path=None,
    )
    assert log.output_path is None


def test_new_run_log_for_loop_with_base_path() -> None:
    """Con base_path, output_path se construye y se crea el folder."""
    with tempfile.TemporaryDirectory() as tmp:
        log = _new_run_log_for_loop(
            loop_name="L", sequence_num=1, run_id="abcdef1234",
            started_at_iso="2026-05-11T10:00:00+00:00",
            config={"loop": {}},
            base_path=Path(tmp),
        )
        assert log.output_path is not None
        assert log.output_path.exists()
        assert "L" in str(log.output_path)
        assert "abcdef" in str(log.output_path)


# ════════════════════════════════════════════════════════════════════
# load_run_logs (carga masiva)
# ════════════════════════════════════════════════════════════════════

def test_load_run_logs_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert load_run_logs(Path(tmp)) == []


def test_load_run_logs_nonexistent() -> None:
    assert load_run_logs(Path("/tmp/non-existent-xyz-789")) == []


def test_load_run_logs_returns_multiple_in_order() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # Crear 3 runs
        for seq, ts in enumerate([
            "2026-05-11T10:00:00+00:00",
            "2026-05-11T10:01:00+00:00",
            "2026-05-11T10:02:00+00:00",
        ], start=1):
            log = _new_run_log_for_loop(
                loop_name="L", sequence_num=seq, run_id=f"{seq:06d}aaaa",
                started_at_iso=ts, config={"loop": {}},
                base_path=base,
            )
            log.write_config()
            log.append_turn(_mk_turn(1))
            log.completed_at = ts
            log.terminated_reason = "max_steps"
            log.write_run_end()

        loaded = load_run_logs(base / "L")
        assert len(loaded) == 3
        # Ordenados por timestamp prefix
        seqs = [l.sequence_num for l in loaded]
        assert seqs == [1, 2, 3]


def test_load_run_logs_skips_incomplete_folders() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "L"
        base.mkdir()
        # Uno completo
        log = _new_run_log_for_loop(
            loop_name="L", sequence_num=1, run_id="aaaaaaa",
            started_at_iso="2026-05-11T10:00:00+00:00",
            config={"loop": {}},
            base_path=Path(tmp),
        )
        log.write_config()
        # Uno vacío
        (base / "fake_folder_no_config").mkdir()
        loaded = load_run_logs(base)
        # Solo carga el completo
        assert len(loaded) == 1
        assert loaded[0].sequence_num == 1


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("runlog_in_memory_no_output_path",          test_runlog_in_memory_no_output_path),
        ("append_turn_in_memory",                    test_append_turn_in_memory),
        ("append_turn_with_output_path_writes_files", test_append_turn_with_output_path_writes_files),
        ("write_config_creates_config_json",         test_write_config_creates_config_json),
        ("write_run_end_creates_run_end_json",       test_write_run_end_creates_run_end_json),
        ("write_config_no_op_when_no_output_path",   test_write_config_no_op_when_no_output_path),
        ("write_full_writes_complete_log",           test_write_full_writes_complete_log),
        ("write_full_raises_if_no_path",             test_write_full_raises_if_no_path),
        ("to_dict_includes_turns_serialized",        test_to_dict_includes_turns_serialized),
        ("from_dict_roundtrip",                      test_from_dict_roundtrip),
        ("load_folder_roundtrip",                    test_load_folder_roundtrip),
        ("compute_run_folder_naming",                test_compute_run_folder_naming),
        ("compute_run_folder_sanitizes_loop_name",   test_compute_run_folder_sanitizes_loop_name),
        ("new_run_log_for_loop_in_memory",           test_new_run_log_for_loop_in_memory),
        ("new_run_log_for_loop_with_base_path",      test_new_run_log_for_loop_with_base_path),
        ("load_run_logs_empty",                      test_load_run_logs_empty),
        ("load_run_logs_nonexistent",                test_load_run_logs_nonexistent),
        ("load_run_logs_returns_multiple_in_order",  test_load_run_logs_returns_multiple_in_order),
        ("load_run_logs_skips_incomplete_folders",   test_load_run_logs_skips_incomplete_folders),
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
