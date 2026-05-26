"""
Tests del public surface sellado en PR 9.

Verifica que:
1. Los nombres v2 listados como públicos están accesibles via
   ``from instantneo import ...``.
2. Las piezas marcadas como subpackage-only NO están en top-level.
3. El legacy ``instantneo.experimental.instant_loop`` emite
   ``DeprecationWarning`` al cargarse, pero sigue funcional.
4. ``__all__`` está bien formado.

Dual-mode.
"""
import sys
import warnings
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ════════════════════════════════════════════════════════════════════
# Public surface v2 — debe estar en top-level
# ════════════════════════════════════════════════════════════════════

def test_v2_history_and_entry_at_top_level() -> None:
    from instantneo import History, Entry
    assert History.__name__ == "History"
    assert Entry.__name__ == "Entry"


def test_v2_monitor_at_top_level() -> None:
    from instantneo import Monitor
    assert Monitor.__name__ == "Monitor"


def test_v2_loop_and_run_result_at_top_level() -> None:
    from instantneo import InstantLoop, RunResult
    assert InstantLoop.__name__ == "InstantLoop"
    assert RunResult.__name__ == "RunResult"


def test_v2_bridge_at_top_level() -> None:
    from instantneo import append_entry_from_run
    assert callable(append_entry_from_run)


def test_v2_queries_at_top_level() -> None:
    from instantneo import (
        current_run_id, current_origin,
        current_run_config, current_step_num,
    )
    assert all(callable(f) for f in (
        current_run_id, current_origin,
        current_run_config, current_step_num,
    ))


def test_clasic_imports_still_work() -> None:
    """Backward compat: InstantNeo, tool, AgentCapabilities, etc. siguen ahí."""
    from instantneo import (
        InstantNeo, RunInfo, tool, AgentCapabilities,
        CapabilitiesOperations,
        skill, SkillManager, SkillManagerOperations,
        Tools, Skills, Adapters,
    )
    assert InstantNeo.__name__ == "InstantNeo"
    assert SkillManager is AgentCapabilities  # alias


# ════════════════════════════════════════════════════════════════════
# Subpackage-only — NO debe estar en top-level
# ════════════════════════════════════════════════════════════════════

def test_rendered_prompt_not_at_top_level() -> None:
    """RenderedPrompt vive en instantneo.loop, no top-level."""
    import instantneo
    assert not hasattr(instantneo, "RenderedPrompt"), \
        "RenderedPrompt no debe estar en top-level (subpackage-only)"
    # Pero SÍ accesible vía subpackage
    from instantneo.loop import RenderedPrompt
    assert RenderedPrompt.__name__ == "RenderedPrompt"


def test_run_log_not_at_top_level() -> None:
    """RunLog (Capa 2) vive en instantneo.loop, no top-level."""
    import instantneo
    assert not hasattr(instantneo, "RunLog"), \
        "RunLog no debe estar en top-level"
    from instantneo.loop import RunLog
    assert RunLog.__name__ == "RunLog"


def test_turn_log_not_at_top_level() -> None:
    """TurnLog vive en instantneo.debug, no top-level."""
    import instantneo
    assert not hasattr(instantneo, "TurnLog"), \
        "TurnLog no debe estar en top-level"
    from instantneo.debug import TurnLog
    assert TurnLog.__name__ == "TurnLog"


def test_monitor_operations_not_at_top_level() -> None:
    """MonitorOperations vive en instantneo.monitor."""
    import instantneo
    assert not hasattr(instantneo, "MonitorOperations"), \
        "MonitorOperations no debe estar en top-level"
    from instantneo.monitor import MonitorOperations
    assert MonitorOperations.union is not None


def test_conditions_actions_not_at_top_level() -> None:
    """Las built-in conditions/actions viven en subpackages."""
    import instantneo
    for name in (
        "when_type_present", "when_last_tool_called", "stop_signal",
        "append_note", "And", "Or", "Not",
    ):
        assert not hasattr(instantneo, name), \
            f"{name} no debe estar en top-level"


def test_write_agent_call_log_not_at_top_level() -> None:
    """Helper de debug vive en instantneo.debug."""
    import instantneo
    assert not hasattr(instantneo, "write_agent_call_log"), \
        "write_agent_call_log no debe estar en top-level"
    from instantneo.debug import write_agent_call_log
    assert callable(write_agent_call_log)


# ════════════════════════════════════════════════════════════════════
# __all__ bien formado
# ════════════════════════════════════════════════════════════════════

def test_all_contains_v2_names() -> None:
    """__all__ del paquete top-level incluye los nombres v2."""
    import instantneo
    expected_v2 = {
        "History", "Entry", "Monitor",
        "InstantLoop", "RunResult",
        "append_entry_from_run",
        "current_run_id", "current_origin",
        "current_run_config", "current_step_num",
    }
    missing = expected_v2 - set(instantneo.__all__)
    assert not missing, f"falta en __all__: {missing}"


def test_all_does_not_include_subpackage_only() -> None:
    """__all__ NO incluye los subpackage-only."""
    import instantneo
    forbidden = {
        "RenderedPrompt", "RunLog", "TurnLog",
        "MonitorOperations",
        "when_type_present", "stop_signal", "append_note",
        "And", "Or", "Not",
        "write_agent_call_log", "load_agent_call_logs",
    }
    leaked = set(instantneo.__all__) & forbidden
    assert not leaked, f"__all__ no debería incluir: {leaked}"


def test_star_import_does_not_leak_internals() -> None:
    """``from instantneo import *`` solo trae lo de __all__."""
    import instantneo
    public_names = set(instantneo.__all__)
    # __all__ debe ser lista de strings
    for n in public_names:
        assert isinstance(n, str)
        assert hasattr(instantneo, n), f"__all__ menciona {n} pero no está en módulo"


# ════════════════════════════════════════════════════════════════════
# Deprecación del legacy
# ════════════════════════════════════════════════════════════════════

def test_legacy_instant_loop_emits_deprecation_warning() -> None:
    """``instantneo.experimental.instant_loop`` debe emitir DeprecationWarning."""
    # Forzar re-import del módulo legacy
    mod_name = "instantneo.experimental.instant_loop"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        import instantneo.experimental.instant_loop  # noqa: F401

        deprecation = [
            w for w in captured
            if issubclass(w.category, DeprecationWarning)
            and "instant_loop" in str(w.message).lower()
        ]
        assert deprecation, "Esperaba DeprecationWarning al cargar legacy"


def test_legacy_instant_loop_still_importable() -> None:
    """El legacy sigue funcional aunque deprecado."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from instantneo.experimental.instant_loop import InstantLoop as LegacyLoop
    # No es la misma clase que la nueva
    from instantneo import InstantLoop as NewLoop
    assert LegacyLoop is not NewLoop
    assert LegacyLoop.__module__ == "instantneo.experimental.instant_loop"
    assert NewLoop.__module__ == "instantneo.loop.instant_loop"


def test_v2_imports_emit_no_warnings() -> None:
    """Importar v2 desde top-level NO debe emitir DeprecationWarning."""
    # Limpiar el cache para forzar re-evaluación
    for mod in list(sys.modules):
        if mod.startswith("instantneo.loop"):
            del sys.modules[mod]

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        from instantneo import InstantLoop, History, Monitor  # noqa: F401

        deprec = [w for w in captured if issubclass(w.category, DeprecationWarning)]
        # No debe haber DeprecationWarning del v2
        v2_deprec = [
            w for w in deprec
            if "instantneo.loop" in str(w.message)
            or "instantneo.history" in str(w.message)
            or "instantneo.monitor" in str(w.message)
        ]
        assert not v2_deprec, f"v2 emitió DeprecationWarning: {v2_deprec}"


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # v2 top-level
        ("v2_history_and_entry_at_top_level",       test_v2_history_and_entry_at_top_level),
        ("v2_monitor_at_top_level",                 test_v2_monitor_at_top_level),
        ("v2_loop_and_run_result_at_top_level",     test_v2_loop_and_run_result_at_top_level),
        ("v2_bridge_at_top_level",                  test_v2_bridge_at_top_level),
        ("v2_queries_at_top_level",                 test_v2_queries_at_top_level),
        ("clasic_imports_still_work",               test_clasic_imports_still_work),
        # subpackage-only
        ("rendered_prompt_not_at_top_level",        test_rendered_prompt_not_at_top_level),
        ("run_log_not_at_top_level",                test_run_log_not_at_top_level),
        ("turn_log_not_at_top_level",               test_turn_log_not_at_top_level),
        ("monitor_operations_not_at_top_level",     test_monitor_operations_not_at_top_level),
        ("conditions_actions_not_at_top_level",     test_conditions_actions_not_at_top_level),
        ("write_agent_call_log_not_at_top_level",   test_write_agent_call_log_not_at_top_level),
        # __all__
        ("all_contains_v2_names",                   test_all_contains_v2_names),
        ("all_does_not_include_subpackage_only",    test_all_does_not_include_subpackage_only),
        ("star_import_does_not_leak_internals",     test_star_import_does_not_leak_internals),
        # Deprecación
        ("legacy_instant_loop_emits_deprecation_warning", test_legacy_instant_loop_emits_deprecation_warning),
        ("legacy_instant_loop_still_importable",    test_legacy_instant_loop_still_importable),
        ("v2_imports_emit_no_warnings",             test_v2_imports_emit_no_warnings),
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
