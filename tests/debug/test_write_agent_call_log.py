"""
Tests de ``write_agent_call_log`` y ``load_agent_call_logs`` (PR 7 Capa 3).

Dual-mode.
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.debug import write_agent_call_log, load_agent_call_logs


# ────────────────────────────────────────────────────────────────────
# Mock agent que satisface la interface mínima del helper
# ────────────────────────────────────────────────────────────────────

class _MockCapabilities:
    def __init__(self, schemas=None):
        self._schemas = schemas or [
            {"type": "function",
             "function": {"name": "my_tool", "description": "x",
                          "parameters": {"type": "object",
                                         "properties": {},
                                         "required": []}}},
        ]
    def get_schemas(self):
        return list(self._schemas)


def _mk_mock_agent(*, with_last_run=True, role_setup="x"):
    run_info = SimpleNamespace(
        error=None, prompt="hola",
        response_content="resp", reasoning=None,
        finish_reason="stop",
        usage={"input_tokens": 5, "output_tokens": 3,
               "total_tokens": 8, "reasoning_tokens": None},
        duration_ms=10.0,
        provider="openai", model="gpt-5-mini",
        timestamp="2026-05-11T10:00:00Z",
        run_params={"model": "gpt-5-mini"},
        provider_timing=None,
        llm_calls=[SimpleNamespace(
            messages_sent=[], response_content="resp",
            finish_reason="stop", tool_calls_requested=[],
            usage=None, response_id="rid", response_model="m",
            reasoning_content=None, raw_response="NOT JSON-SAFE")],
        tool_executions=[],
        messages_sent=[{"role": "user", "content": "hola"}],
    ) if with_last_run else None

    config = SimpleNamespace(
        provider="openai", model="gpt-5-mini",
        api_key="sk-test-SHOULD-NOT-LEAK",
        role_setup=role_setup,
        temperature=0.7, max_tokens=100,
        presence_penalty=None, frequency_penalty=None,
        stop=None, seed=None, stream=False, logit_bias=None,
        images=None, image_detail="auto",
        service_account_file=None, location=None,
    )

    class _Agent:
        def __init__(self):
            self.last_run = run_info
            self.config = config
            self.capabilities = _MockCapabilities()
        def get_resolved_role_setup(self, shelf_context=None):
            return f"{role_setup}{(' + ' + shelf_context) if shelf_context else ''}"
    return _Agent()


# ════════════════════════════════════════════════════════════════════
# write_agent_call_log — happy paths
# ════════════════════════════════════════════════════════════════════

def test_write_creates_config_and_call_json() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        written = write_agent_call_log(agent, folder)
        assert written.exists() and written.is_dir()
        assert (written / "config.json").exists()
        assert (written / "call.json").exists()


def test_write_returns_resolved_path() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "x"
        written = write_agent_call_log(agent, folder)
        # Resolved es absoluto
        assert written.is_absolute()


def test_write_config_has_expected_shape() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        written = write_agent_call_log(agent, folder)
        cfg = json.loads((written / "config.json").read_text())
        assert "agent" in cfg
        assert "captured_at" in cfg
        assert "call_id" in cfg
        assert cfg["agent"]["provider"] == "openai"
        assert cfg["agent"]["model"] == "gpt-5-mini"


def test_write_does_not_leak_api_key() -> None:
    """REQUISITO CRÍTICO: api_key nunca debe quedar en el JSON."""
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        written = write_agent_call_log(agent, folder)
        config_text = (written / "config.json").read_text()
        assert "sk-test-SHOULD-NOT-LEAK" not in config_text
        assert "api_key" not in config_text


def test_write_call_json_has_turnlog_shape() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        written = write_agent_call_log(agent, folder)
        call = json.loads((written / "call.json").read_text())
        # Campos del shape de TurnLog
        for k in ("step_num", "started_at", "completed_at", "prompt",
                  "messages_sent", "run_params", "response_content",
                  "provider", "model", "request_started_at"):
            assert k in call, f"falta key {k}"
        assert call["step_num"] == 1


def test_write_call_id_provided_preserved() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        written = write_agent_call_log(agent, folder, call_id="my-fixed-id-001")
        cfg = json.loads((written / "config.json").read_text())
        assert cfg["call_id"] == "my-fixed-id-001"


def test_write_call_id_autogenerated_when_omitted() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        written = write_agent_call_log(agent, folder)
        cfg = json.loads((written / "config.json").read_text())
        assert isinstance(cfg["call_id"], str)
        assert len(cfg["call_id"]) > 0


def test_write_extra_is_included_when_provided() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        written = write_agent_call_log(
            agent, folder, extra={"experiment": "v2", "user": "alice"},
        )
        cfg = json.loads((written / "config.json").read_text())
        assert cfg["extra"] == {"experiment": "v2", "user": "alice"}


def test_write_no_extra_means_no_extra_key() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        written = write_agent_call_log(agent, folder)
        cfg = json.loads((written / "config.json").read_text())
        assert "extra" not in cfg


def test_write_creates_folder_if_not_exists() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "deep" / "nested" / "non-existent"
        written = write_agent_call_log(agent, folder)
        assert written.exists()


# ════════════════════════════════════════════════════════════════════
# write_agent_call_log — errores
# ════════════════════════════════════════════════════════════════════

def test_write_raises_when_no_last_run() -> None:
    agent = _mk_mock_agent(with_last_run=False)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "call"
        try:
            write_agent_call_log(agent, folder)
        except RuntimeError as e:
            assert "last_run" in str(e).lower()
            return
        raise AssertionError("Esperaba RuntimeError")


# ════════════════════════════════════════════════════════════════════
# load_agent_call_logs
# ════════════════════════════════════════════════════════════════════

def test_load_empty_folder_returns_empty_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert load_agent_call_logs(Path(tmp)) == []


def test_load_nonexistent_folder_returns_empty_list() -> None:
    """No crashea con folder inexistente."""
    assert load_agent_call_logs(Path("/tmp/non-existent-xyz-123")) == []


def test_load_returns_written_calls() -> None:
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        write_agent_call_log(agent, base / "20260511_100000_call_001_aaa")
        write_agent_call_log(agent, base / "20260511_100100_call_002_bbb")
        write_agent_call_log(agent, base / "20260511_100200_call_003_ccc")

        loaded = load_agent_call_logs(base)
        assert len(loaded) == 3
        # Cada uno tiene folder, config, call
        for entry in loaded:
            assert set(entry.keys()) == {"folder", "config", "call"}
            assert isinstance(entry["folder"], Path)


def test_load_orders_by_folder_name() -> None:
    """Folders con timestamp prefix lex-sortable salen en orden."""
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # Creados desordenados, mismo agent
        write_agent_call_log(agent, base / "20260511_100200_call_003")
        write_agent_call_log(agent, base / "20260511_100000_call_001")
        write_agent_call_log(agent, base / "20260511_100100_call_002")

        loaded = load_agent_call_logs(base)
        names = [entry["folder"].name for entry in loaded]
        assert names == [
            "20260511_100000_call_001",
            "20260511_100100_call_002",
            "20260511_100200_call_003",
        ]


def test_load_skips_folders_without_both_files() -> None:
    """Subfolders sin config.json o call.json se skippean (no crashean)."""
    agent = _mk_mock_agent()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # Uno completo
        write_agent_call_log(agent, base / "complete")
        # Uno incompleto (solo config.json)
        partial = base / "partial"
        partial.mkdir()
        (partial / "config.json").write_text("{}")
        # Uno vacío
        (base / "empty").mkdir()

        loaded = load_agent_call_logs(base)
        # Solo el completo carga
        assert len(loaded) == 1
        assert loaded[0]["folder"].name == "complete"


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("write_creates_config_and_call_json",        test_write_creates_config_and_call_json),
        ("write_returns_resolved_path",                test_write_returns_resolved_path),
        ("write_config_has_expected_shape",            test_write_config_has_expected_shape),
        ("write_does_not_leak_api_key",                test_write_does_not_leak_api_key),
        ("write_call_json_has_turnlog_shape",          test_write_call_json_has_turnlog_shape),
        ("write_call_id_provided_preserved",           test_write_call_id_provided_preserved),
        ("write_call_id_autogenerated_when_omitted",   test_write_call_id_autogenerated_when_omitted),
        ("write_extra_is_included_when_provided",      test_write_extra_is_included_when_provided),
        ("write_no_extra_means_no_extra_key",          test_write_no_extra_means_no_extra_key),
        ("write_creates_folder_if_not_exists",         test_write_creates_folder_if_not_exists),
        ("write_raises_when_no_last_run",              test_write_raises_when_no_last_run),
        ("load_empty_folder_returns_empty_list",       test_load_empty_folder_returns_empty_list),
        ("load_nonexistent_folder_returns_empty_list", test_load_nonexistent_folder_returns_empty_list),
        ("load_returns_written_calls",                 test_load_returns_written_calls),
        ("load_orders_by_folder_name",                 test_load_orders_by_folder_name),
        ("load_skips_folders_without_both_files",      test_load_skips_folders_without_both_files),
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
