"""
Ejemplo 11 — debug=True → RunLog forensic en disco
=====================================================

Caso funcional
--------------
Cuando algo sale raro en producción ("el agente respondió mal en este
run", "se gastó muchísimos tokens", "una tool devolvió algo inesperado"),
el History tiene la trazabilidad narrativa, pero no el detalle
forensic per-turno: los mensajes EXACTOS enviados al provider, los
tokens consumidos por step, los timings, los reasoning tokens, la
cabecera del agente, etc.

Para eso existe el **RunLog**, el sistema de debug opt-in del Loop. Se
activa pasando `debug=True` al construir el `InstantLoop`. A partir de
ahí, cada `loop.run()` escribe un folder a disco con un dump completo:

  - **`config.json`**: cabecera self-contained del run (agent config
    con role_setup resuelto + tool schemas; loop config; input).
  - **`turn_NNN.json`**: un `TurnLog` por cada step del agente, con
    messages_sent, usage, tool_executions, provider_timing, etc.
  - **`run_end.json`**: terminated_reason, stop_reason, duración total.

El RunLog es **independiente del History**. El History queda lean
(solo entries narrativas); el RunLog acumula el detalle forensic. Eso
te permite tener auditoría detallada sin engordar la memoria del
agente.

Qué muestra este ejemplo
------------------------
1. Construimos un Loop con `debug=True` y `debug_base_path` apuntando
   a un directorio temporal.
2. Corremos una tarea que toma 3 steps.
3. Inspeccionamos los archivos generados en disco.
4. Mostramos el contenido relevante de `config.json` (cabecera).
5. Mostramos el shape de un `turn_NNN.json` (TurnLog forensic).
6. Recargamos el folder con `RunLog.load_folder(...)` y verificamos
   que reconstruye el log entero — útil para evaluaciones offline.

Cómo correr
-----------
    python3 examples/11_debug_runlog.py
"""
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env", override=True)
except ImportError:
    pass

from instantneo import History, InstantLoop, InstantNeo, tool
# RunLog y load_run_logs viven en `instantneo.loop` — no en el
# top-level por minimalismo. Si necesitas TurnLog suelto, viene de
# `instantneo.debug`.
from instantneo.loop import RunLog, load_run_logs


# ────────────────────────────────────────────────────────────────────
# Tools
# ────────────────────────────────────────────────────────────────────
ALERTAS_ACTIVAS = [
    {"id": "A1", "tipo": "disco",   "nivel": "media"},
    {"id": "A2", "tipo": "memoria", "nivel": "crítica"},
]
DETALLES = {
    "A1": "Disco al 78% en /var. Logs sin rotar.",
    "A2": "Memoria al 95% en pagos-api. Posible memory leak.",
}


@tool(description="Lista las alertas activas del sistema.", parameters={})
def obtener_alertas() -> list:
    return ALERTAS_ACTIVAS


@tool(
    description="Devuelve el detalle de una alerta por su ID.",
    parameters={"alerta_id": {"description": "ID de la alerta.", "type": "string"}},
)
def obtener_detalle_alerta(alerta_id: str) -> dict:
    return {"id": alerta_id, "descripcion": DETALLES.get(alerta_id, "?")}


@tool(
    description="Entrega la respuesta final al usuario.",
    parameters={"mensaje": {"description": "Respuesta.", "type": "string"}},
)
def responder(mensaje: str) -> dict:
    return {"mensaje": mensaje}


PROVIDER = "openai"
MODEL = "gpt-4.1-mini"
API_KEY = os.environ.get("OPEN_AI_API_KEY")

if not API_KEY:
    print("ERROR: falta OPEN_AI_API_KEY en el entorno.")
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────
# Directorio temporal para los logs
# ────────────────────────────────────────────────────────────────────
DEBUG_DIR = Path("/tmp/instantneo_ejemplo11_debug")


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    # Limpieza para que el ejemplo sea reproducible.
    if DEBUG_DIR.exists():
        import shutil
        shutil.rmtree(DEBUG_DIR)

    # ────────────────────────────────────────────────────────────────
    # 1. Loop con debug=True
    # ────────────────────────────────────────────────────────────────
    # Las dos kwargs clave:
    #   debug=True            → activa el RunLog.
    #   debug_base_path=path  → raíz donde se crearán los folders.
    # El layout que se genera:
    #   <debug_base_path>/<loop_name>/<YYYYMMDD_HHMMSS>_run_NNN_<run_id6>/
    history = History(name="chat_debug_demo")
    agente = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup=(
            "Eres un asistente de operaciones. Investiga las alertas y "
            "emite un reporte priorizado. Al final llama `responder`."
        ),
        tools=[obtener_alertas, obtener_detalle_alerta, responder],
    )
    agente.name = "agente_operador"

    loop = InstantLoop(
        agent=agente,
        history=history,
        name="loop_operador",
        stop_tool="responder",
        max_steps=6,
        debug=True,                       # ← acá se activa
        debug_base_path=DEBUG_DIR,        # ← acá se escribe
    )

    # ────────────────────────────────────────────────────────────────
    # 2. Correr una tarea
    # ────────────────────────────────────────────────────────────────
    section("EJECUTANDO EL LOOP CON DEBUG=TRUE")
    print(f"  debug_base_path: {DEBUG_DIR}")
    result = loop.run(
        "Revisa las alertas y emite un reporte priorizado con la "
        "acción recomendada para la más crítica."
    )
    print(f"  resultado: {result.terminated_reason} ({result.total_steps} steps)")

    # ────────────────────────────────────────────────────────────────
    # 3. Inspección de archivos generados
    # ────────────────────────────────────────────────────────────────
    section("ARCHIVOS GENERADOS EN DISCO")
    # Estructura: DEBUG_DIR/<loop_name>/<timestamp_run_seq_id>/
    loop_folder = DEBUG_DIR / "loop_operador"
    run_folders = sorted(loop_folder.iterdir())
    run_folder = run_folders[-1]
    print(f"  loop folder : {loop_folder}")
    print(f"  run folder  : {run_folder.name}")
    print(f"  archivos    :")
    for archivo in sorted(run_folder.iterdir()):
        size_kb = archivo.stat().st_size / 1024
        print(f"    - {archivo.name:<20} ({size_kb:5.1f} KB)")

    # ────────────────────────────────────────────────────────────────
    # 4. Contenido de config.json (cabecera self-contained)
    # ────────────────────────────────────────────────────────────────
    # `config.json` es la "cabecera" del run: contiene todo lo
    # necesario para reproducirlo (provider, modelo, role_setup
    # resuelto con tool_instructions ya inyectadas, tool schemas,
    # input). Es self-contained — no necesitas otro archivo para
    # entender qué se ejecutó.
    section("config.json — top-level keys")
    config_data = json.loads((run_folder / "config.json").read_text())
    for k, v in config_data.items():
        if isinstance(v, dict):
            sub_keys = ", ".join(v.keys())
            print(f"  {k:<14}: dict  → keys: {sub_keys}")
        else:
            preview = str(v)[:60]
            print(f"  {k:<14}: {type(v).__name__:<5} → {preview}")

    print()
    print("  agent.provider  :", config_data["agent"]["provider"])
    print("  agent.model     :", config_data["agent"]["model"])
    print("  agent.tools     : [", ", ".join(
        t["function"]["name"] for t in config_data["agent"]["tools"]
    ), "]")
    print("  loop.max_steps  :", config_data["loop"]["max_steps"])
    print("  loop.stop_tool  :", config_data["loop"]["stop_tool"])
    print("  input.prompt    :", config_data["input"]["prompt"][:60], "...")

    # ────────────────────────────────────────────────────────────────
    # 5. Contenido de un turn — el forensic real
    # ────────────────────────────────────────────────────────────────
    # Cada `turn_NNN.json` es un `TurnLog` con TODO el detalle de un
    # step: los messages_sent enviados al provider literal, el
    # run_params efectivos, el response_content, los tool_executions
    # (con args y results nativos, no stringificados), usage,
    # duration, provider_timing.
    section("turn_001.json — campos del TurnLog")
    turn1 = json.loads((run_folder / "turn_001.json").read_text())
    for k in [
        "step_num", "started_at", "completed_at", "duration_ms",
        "provider", "model", "finish_reason", "usage", "response_id",
    ]:
        if k in turn1:
            print(f"  {k:<18}: {turn1[k]}")
    print(f"  prompt (primeros 80 chars):")
    print(f"    {str(turn1.get('prompt', ''))[:80]}...")
    print(f"  tool_executions  : {len(turn1.get('tool_executions', []))} tools")
    for te in turn1.get("tool_executions", []):
        print(f"    - {te.get('name')}({te.get('arguments')}) → "
              f"{str(te.get('result'))[:60]}...")

    # ────────────────────────────────────────────────────────────────
    # 6. Contenido de run_end.json (cierre)
    # ────────────────────────────────────────────────────────────────
    section("run_end.json — metadata de cierre del run")
    run_end = json.loads((run_folder / "run_end.json").read_text())
    for k, v in run_end.items():
        print(f"  {k:<20}: {v}")

    # ────────────────────────────────────────────────────────────────
    # 7. Recarga del log con RunLog.load_folder() — para análisis offline
    # ────────────────────────────────────────────────────────────────
    # `load_folder` lee config + todos los turn_NNN.json + run_end.json
    # y reconstruye un objeto `RunLog` con `turns: list[TurnLog]`. Útil
    # para análisis offline: evaluación de runs en batch, comparación
    # entre versiones del agente, dashboards, etc.
    section("RECARGA OFFLINE — RunLog.load_folder(run_folder)")
    runlog = RunLog.load_folder(run_folder)
    print(f"  loop_name        : {runlog.loop_name}")
    print(f"  sequence_num     : {runlog.sequence_num}")
    print(f"  run_id           : {runlog.run_id}")
    print(f"  total_steps      : {len(runlog.turns)}")
    print(f"  terminated_reason: {runlog.terminated_reason}")
    print(f"  stop_reason      : {runlog.stop_reason}")
    print(f"  total tokens     : ", sum(
        (t.usage or {}).get("total_tokens", 0) for t in runlog.turns
    ))

    # `load_run_logs` carga TODOS los runs de un loop_folder. Útil
    # cuando un mismo loop tiene varios runs (multi-sesión, varias
    # invocaciones consecutivas) y querés analizarlos todos.
    section("CARGAR TODOS LOS RUNS DE UN LOOP — load_run_logs()")
    todos = load_run_logs(loop_folder)
    print(f"  runs encontrados: {len(todos)}")
    for r in todos:
        print(f"    - run_id={r.run_id[:8]}... seq={r.sequence_num} "
              f"steps={len(r.turns)} reason={r.terminated_reason}")

    # ────────────────────────────────────────────────────────────────
    # Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    # 1. Estructura de archivos esperada.
    assert (run_folder / "config.json").exists()
    assert (run_folder / "run_end.json").exists()
    assert len(list(run_folder.glob("turn_*.json"))) == result.total_steps
    # 2. El RunLog reconstruido coincide con lo que sucedió.
    assert runlog.run_id == result.run_id
    assert runlog.terminated_reason == result.terminated_reason
    assert len(runlog.turns) == result.total_steps

    print("\n✅ Ejemplo 11 completado correctamente.")
    print(f"  los archivos quedan en {DEBUG_DIR} (los podés inspeccionar)")


if __name__ == "__main__":
    main()
