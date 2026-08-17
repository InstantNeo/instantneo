"""
Tests del gate de scope en la ejecución de tools.

Regresión de S1 (revisión de seguridad, docs/security-architecture-review.md):
``run(tools=[...])`` calculaba ``active_tools`` pero solo lo usaba para
armar los schemas que se le mandan al provider. ``_handle_tool_calls``
validaba contra ``self.get_tool_names()`` — el registro completo — así
que un tool_call fuera del scope se ejecutaba igual.

Cubre además:
- Que la violación quede registrada en el RunInfo (visible en History
  y RunLog), no solo en un warning.
- Que un JSON de argumentos malformado no tumbe el run entero.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
import json

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo import InstantNeo, tool
from instantneo.models.run_info import RunInfo


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

_EXECUTED: list[str] = []


@tool(description="Tool inocua", parameters={"x": {"description": "num", "type": "int"}})
def safe_tool(x: int = 1) -> str:
    _EXECUTED.append("safe_tool")
    return "safe"


@tool(description="Tool destructiva", parameters={"target": {"description": "db", "type": "str"}})
def delete_database(target: str = "prod") -> str:
    _EXECUTED.append("delete_database")
    return f"DROPPED {target}"


def _mk_agent() -> InstantNeo:
    return InstantNeo(
        provider="openai", model="gpt-5-mini", api_key="sk-test",
        role_setup="Sos un asistente.",
        skills=[safe_tool, delete_database],
    )


def _tool_call(name: str, args) -> SimpleNamespace:
    """Simula el objeto tool_call que devuelve el adapter."""
    raw = args if isinstance(args, str) else json.dumps(args)
    return SimpleNamespace(
        type="function",
        function=SimpleNamespace(name=name, arguments=raw),
    )


def _mk_run_info() -> RunInfo:
    return RunInfo(
        provider="openai", model="gpt-5-mini", prompt="p",
        execution_mode="wait_response", stream=False, timestamp="2026-01-01T00:00:00Z",
    )


# ────────────────────────────────────────────────────────────────────
# El gate de scope
# ────────────────────────────────────────────────────────────────────

def test_tool_fuera_de_scope_no_se_ejecuta() -> None:
    """El PoC de S1: un run limitado a safe_tool no ejecuta delete_database."""
    _EXECUTED.clear()
    agent = _mk_agent()
    active = agent._get_active_tools(["safe_tool"])

    agent._handle_tool_calls(
        [_tool_call("delete_database", {"target": "prod"})],
        "wait_response", _mk_run_info(), active_tools=active,
    )

    assert _EXECUTED == [], "se ejecutó una tool fuera del scope del run"


def test_tool_fuera_de_scope_queda_registrada_en_run_info() -> None:
    """La violación tiene que ser visible, no un warning que se pierde."""
    _EXECUTED.clear()
    agent = _mk_agent()
    active = agent._get_active_tools(["safe_tool"])
    run_info = _mk_run_info()

    agent._handle_tool_calls(
        [_tool_call("delete_database", {"target": "prod"})],
        "wait_response", run_info, active_tools=active,
    )

    assert len(run_info.tool_executions) == 1
    exec_record = run_info.tool_executions[0]
    assert exec_record.name == "delete_database"
    assert exec_record.result is None
    assert "fuera del scope" in (exec_record.exception or "")


def test_tool_dentro_de_scope_si_se_ejecuta() -> None:
    """El gate no puede romper el camino feliz."""
    _EXECUTED.clear()
    agent = _mk_agent()
    active = agent._get_active_tools(["safe_tool"])

    result = agent._handle_tool_calls(
        [_tool_call("safe_tool", {"x": 1})],
        "wait_response", _mk_run_info(), active_tools=active,
    )

    assert _EXECUTED == ["safe_tool"]
    assert result == "safe"


def test_scope_se_aplica_tambien_en_get_args() -> None:
    """GET_ARGS no ejecuta, pero tampoco debe reportar tools fuera de scope."""
    agent = _mk_agent()
    active = agent._get_active_tools(["safe_tool"])

    results = agent._handle_tool_calls(
        [_tool_call("delete_database", {"target": "prod"})],
        "get_args", _mk_run_info(), active_tools=active,
    )

    assert results == []


def test_execute_tool_rechaza_nombre_fuera_de_scope() -> None:
    """``_execute_tool`` es el punto único de resolución y aplica el scope."""
    _EXECUTED.clear()
    agent = _mk_agent()
    active = agent._get_active_tools(["safe_tool"])

    try:
        agent._execute_tool("delete_database", {"target": "prod"}, active)
    except ValueError as e:
        assert "fuera del scope" in str(e)
    else:
        raise AssertionError("_execute_tool ejecutó una tool fuera del scope")

    assert _EXECUTED == []


def test_omitir_active_tools_es_error_no_permiso_total() -> None:
    """El gate falla cerrado: sin scope no se ejecuta nada.

    ``active_tools`` es keyword-only y obligatorio a propósito. Un
    default permisivo reproduciría el bug original — un call site que
    olvida pasar el scope desactivaría el gate en silencio.
    """
    _EXECUTED.clear()
    agent = _mk_agent()

    try:
        agent._handle_tool_calls(
            [_tool_call("delete_database", {"target": "x"})],
            "wait_response", _mk_run_info(),
        )
    except TypeError:
        pass
    else:
        raise AssertionError("_handle_tool_calls aceptó omitir active_tools")

    assert _EXECUTED == []


def test_scope_vacio_no_ejecuta_nada() -> None:
    """Un run sin tools activas no ejecuta ninguna, aunque estén registradas."""
    _EXECUTED.clear()
    agent = _mk_agent()
    run_info = _mk_run_info()

    agent._handle_tool_calls(
        [_tool_call("delete_database", {"target": "x"})],
        "wait_response", run_info, active_tools={},
    )

    assert _EXECUTED == []
    assert "fuera del scope" in (run_info.tool_executions[0].exception or "")


def test_registro_completo_requiere_pedirlo_explicitamente() -> None:
    """Ejecutar contra todo el registro sigue siendo posible, pero explícito."""
    _EXECUTED.clear()
    agent = _mk_agent()
    todas = agent._get_active_tools(agent.get_tool_names())

    agent._handle_tool_calls(
        [_tool_call("delete_database", {"target": "x"})],
        "wait_response", _mk_run_info(), active_tools=todas,
    )

    assert _EXECUTED == ["delete_database"]


def test_tool_inexistente_no_rompe() -> None:
    _EXECUTED.clear()
    agent = _mk_agent()
    active = agent._get_active_tools(["safe_tool"])
    run_info = _mk_run_info()

    agent._handle_tool_calls(
        [_tool_call("no_existe", {})], "wait_response", run_info, active_tools=active,
    )

    assert _EXECUTED == []
    assert run_info.tool_executions[0].exception is not None


# ────────────────────────────────────────────────────────────────────
# Argumentos malformados
# ────────────────────────────────────────────────────────────────────

def test_json_malformado_no_tumba_el_run() -> None:
    """Un provider que devuelve JSON truncado no puede abortar el run.

    Dentro de un InstantLoop eso tiraba todos los steps ya pagados.
    """
    agent = _mk_agent()
    active = agent._get_active_tools(["safe_tool"])
    run_info = _mk_run_info()

    agent._handle_tool_calls(
        [_tool_call("safe_tool", '{"x": ')], "wait_response", run_info, active_tools=active,
    )

    assert len(run_info.tool_executions) == 1
    assert "inválidos" in (run_info.tool_executions[0].exception or "")


def test_args_null_se_tratan_como_dict_vacio() -> None:
    """Comportamiento heredado: `null` -> llamada sin args, no crash."""
    _EXECUTED.clear()
    agent = _mk_agent()
    active = agent._get_active_tools(["safe_tool"])

    agent._handle_tool_calls(
        [_tool_call("safe_tool", "null")], "wait_response", _mk_run_info(), active_tools=active,
    )

    assert _EXECUTED == ["safe_tool"]


TESTS = [
    ("tool_fuera_de_scope_no_se_ejecuta", test_tool_fuera_de_scope_no_se_ejecuta),
    ("tool_fuera_de_scope_queda_registrada", test_tool_fuera_de_scope_queda_registrada_en_run_info),
    ("tool_dentro_de_scope_si_se_ejecuta", test_tool_dentro_de_scope_si_se_ejecuta),
    ("scope_se_aplica_en_get_args", test_scope_se_aplica_tambien_en_get_args),
    ("execute_tool_rechaza_fuera_de_scope", test_execute_tool_rechaza_nombre_fuera_de_scope),
    ("omitir_active_tools_es_error", test_omitir_active_tools_es_error_no_permiso_total),
    ("scope_vacio_no_ejecuta_nada", test_scope_vacio_no_ejecuta_nada),
    ("registro_completo_es_explicito", test_registro_completo_requiere_pedirlo_explicitamente),
    ("tool_inexistente_no_rompe", test_tool_inexistente_no_rompe),
    ("json_malformado_no_tumba_el_run", test_json_malformado_no_tumba_el_run),
    ("args_null_como_dict_vacio", test_args_null_se_tratan_como_dict_vacio),
]


if __name__ == "__main__":
    for name, fn in TESTS:
        fn()
        print(f"  OK  {name}")
    print(f"\n{len(TESTS)} tests pasaron.")
