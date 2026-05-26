"""
Ejemplo 04 — Vista custom: tu propio prompt
============================================

Caso funcional
--------------
Has visto cómo `loop_default` renderea el History para el modelo. Pero
ese formato no siempre encaja: el log crece con cada turno, y en loops
largos los tokens (y el costo) se disparan. Una solución concreta y
realista es una **vista con ventana deslizante**: en lugar de incluir
toda la historia, mantienes el prompt inicial del usuario más solo los
últimos N turnos de actividad. El agente preserva el norte de la tarea
y los pasos recientes, pero olvida lo lejano.

Eso es lo que hacemos en este ejemplo. Escribimos una vista propia, la
registramos en el History, y le decimos al Loop que la use en lugar de
`loop_default`.

Qué muestra este ejemplo
------------------------
1. **Una vista es solo una función** `History → str | RenderedPrompt`.
   Sin clase base, sin herencia, sin plugin. Devolver `str` también es
   válido: el Loop lo envuelve internamente.
2. **Cómo registrarla**: `history.add_view("nombre", funcion)`.
3. **Cómo decirle al Loop que la use**: `InstantLoop(view="nombre", ...)`.
4. **Factory pattern** para vistas parametrizadas: como `history.add_view`
   recibe una callable sin args (la vista solo recibe el History al
   ejecutarse), si tu vista necesita configuración la fabricamos con un
   factory que devuelve un closure.
5. **Comparación lado a lado**: al final del run, exportamos las dos
   vistas (la custom y `loop_default`) para que veas concretamente qué
   cambió.

Cómo correr
-----------
    python3 examples/04_custom_view.py
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
# Importamos la vista default desde su sub-paquete para poder registrarla
# manualmente y compararla con la nuestra al final.
from instantneo.loop.default_view import loop_default
# `current_run_id` filtra entries del run actual (ignora entries de
# corridas anteriores si las hubiera, lo que importa cuando un History
# acumula múltiples runs).
from instantneo.history.queries import current_run_id


# ────────────────────────────────────────────────────────────────────
# Tools (mismas que en ejemplos anteriores)
# ────────────────────────────────────────────────────────────────────
ALERTAS_ACTIVAS = [
    {"id": "A1", "tipo": "disco",   "nivel": "media"},
    {"id": "A2", "tipo": "memoria", "nivel": "crítica"},
    {"id": "A3", "tipo": "red",     "nivel": "baja"},
]
DETALLES_ALERTAS = {
    "A1": "Disco al 78% en /var.",
    "A2": "Uso de memoria al 95% en el servidor de aplicaciones.",
    "A3": "Latencia de red de 250ms hacia el data center secundario.",
}


@tool(description="Lista las alertas activas del sistema.", parameters={})
def obtener_alertas() -> list:
    return ALERTAS_ACTIVAS


@tool(
    description="Devuelve el detalle de una alerta por su ID.",
    parameters={"alerta_id": {"description": "ID de la alerta.", "type": "string"}},
)
def obtener_detalle_alerta(alerta_id: str) -> dict:
    return {"id": alerta_id, "descripcion": DETALLES_ALERTAS.get(alerta_id, "?")}


@tool(
    description="Llama esta función cuando hayas terminado el análisis.",
    parameters={
        "alerta_critica_id": {"description": "ID de la más crítica.", "type": "string"},
        "resumen": {"description": "Resumen en una o dos oraciones.", "type": "string"},
        "accion_recomendada": {"description": "Próxima acción.", "type": "string"},
    },
)
def reportar(alerta_critica_id: str, resumen: str, accion_recomendada: str) -> dict:
    return {
        "alerta_critica_id": alerta_critica_id,
        "resumen": resumen,
        "accion_recomendada": accion_recomendada,
    }


PROVIDER = "openai"
MODEL = "gpt-4.1-mini"
API_KEY = os.environ.get("OPEN_AI_API_KEY")

if not API_KEY:
    print("ERROR: falta OPEN_AI_API_KEY en el entorno.")
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────
# La vista custom: ventana deslizante
# ────────────────────────────────────────────────────────────────────
# Devuelve una callable `History → str` que renderea:
#   - El prompt inicial del usuario (siempre, para preservar la tarea).
#   - Los últimos `ventana` turnos de actividad (response + tool_call).
# Las entries internas del orchestrator (run_start, step_*) las ignora,
# igual que `loop_default`.
def crear_vista_compacta(ventana: int = 2):
    """Factory: devuelve una vista que mantiene el prompt inicial y los
    últimos `ventana` turnos. El parámetro `ventana` queda capturado en
    el closure — el History no le pasa argumentos a la vista al
    ejecutarla."""

    def vista_compacta(history) -> str:
        # 1. Identificar el run actual. Si tu History acumula varios runs
        #    (multi-run), esta línea garantiza que solo miras el actual.
        rid = current_run_id(history)

        # 2. Prompt inicial del usuario para este run.
        prompts = [
            e for e in history.by_type("prompt")
            if isinstance(e.content, dict) and e.content.get("run_id") == rid
        ]
        prompt_text = prompts[0].content.get("text", "") if prompts else ""

        # 3. Entries narrativas (response + tool_call) del run, ordenadas
        #    por id (cronológico) y agrupadas por turno.
        eventos = []
        for tipo in ("response", "tool_call"):
            for e in history.by_type(tipo):
                if isinstance(e.content, dict) and e.content.get("run_id") == rid:
                    eventos.append(e)
        eventos.sort(key=lambda e: e.id)

        turnos: dict[int, list] = {}
        for e in eventos:
            tn = e.content.get("turn_num", 0)
            turnos.setdefault(tn, []).append(e)

        # 4. Aplicar la ventana: solo los últimos N turnos.
        turnos_visibles = sorted(turnos.keys())[-ventana:]

        # 5. Formato narrativo simple.
        lines = [f"Tarea original: {prompt_text}", ""]
        if not turnos_visibles:
            lines.append("(Aún no has ejecutado ninguna acción. Comienza la tarea.)")
        else:
            lines.append(f"Tus acciones recientes (ventana={ventana}):")
            for tn in turnos_visibles:
                for e in turnos[tn]:
                    c = e.content
                    if e.type == "response":
                        text = (c.get("text") or "").strip()
                        if text:
                            lines.append(f"  T{tn} — respondiste: {text}")
                    elif e.type == "tool_call":
                        name = c.get("name")
                        args = c.get("arguments") or {}
                        result = c.get("result")
                        # Resultado compacto: primeros 180 chars.
                        result_str = json.dumps(result, ensure_ascii=False, default=str)
                        if len(result_str) > 180:
                            result_str = result_str[:180] + "..."
                        lines.append(f"  T{tn} — llamaste {name}({args}) → {result_str}")
        return "\n".join(lines)

    return vista_compacta


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    # ────────────────────────────────────────────────────────────────
    # 1. Creamos el History y registramos nuestra vista
    # ────────────────────────────────────────────────────────────────
    # El registro tiene que ocurrir ANTES de construir el Loop. Si le
    # pasas `view="compacta"` al Loop sin haber registrado la vista, el
    # Loop lanza `LoopConfigError`.
    history = History(name="vista_custom_demo")
    history.add_view("compacta", crear_vista_compacta(ventana=2))

    # Adicionalmente registramos `loop_default` para poder comparar al
    # final. El Loop NO la registra automáticamente porque le decimos
    # `view="compacta"` — solo registra la vista que va a usar.
    history.add_view("loop_default", loop_default)

    section("VISTAS REGISTRADAS EN EL HISTORY")
    print(f"  history.list_views() → {history.list_views()}")

    # ────────────────────────────────────────────────────────────────
    # 2. Agente + Loop con la vista custom
    # ────────────────────────────────────────────────────────────────
    agent = InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup=(
            "Eres un asistente de operaciones. Revisa las alertas, identifica "
            "la más crítica, obtén su detalle y reporta con una acción "
            "recomendada. Usa siempre las tools."
        ),
        tools=[obtener_alertas, obtener_detalle_alerta, reportar],
    )
    loop = InstantLoop(
        agent=agent,
        history=history,
        name="ejemplo_04",
        view="compacta",        # ← el Loop usa la vista que registramos
        stop_tool="reportar",
        max_steps=8,
    )

    # ────────────────────────────────────────────────────────────────
    # 3. Corremos
    # ────────────────────────────────────────────────────────────────
    print()
    print(">>> Ejecutando el loop con la vista compacta...")
    result = loop.run("Revisa las alertas y emite un reporte.")
    print(f">>> Terminó: {result.terminated_reason} en {result.total_steps} steps")

    # ────────────────────────────────────────────────────────────────
    # 4. Comparación: vista compacta vs. loop_default
    # ────────────────────────────────────────────────────────────────
    # Las dos vistas leen el MISMO history. La diferencia está en qué
    # filtran y cómo formatean.
    texto_compacto = history.export("compacta")
    texto_default = history.export("loop_default").text  # loop_default devuelve RenderedPrompt

    section(f"VISTA COMPACTA — {len(texto_compacto)} chars")
    print(texto_compacto)

    section(f"VISTA loop_default — {len(texto_default)} chars")
    print(texto_default)

    section("DIFERENCIA EN UNA LÍNEA")
    ahorro = len(texto_default) - len(texto_compacto)
    pct = ahorro * 100 // max(len(texto_default), 1)
    print(f"  loop_default = {len(texto_default)} chars")
    print(f"  compacta     = {len(texto_compacto)} chars")
    print(f"  ahorro       = {ahorro} chars ({pct}%)")
    print(f"  el primer turno (obtener_alertas con la lista entera)")
    print(f"  queda fuera de la vista compacta, dentro de loop_default.")

    # ────────────────────────────────────────────────────────────────
    # 5. Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    assert result.terminated_reason == "stop_signal"
    assert "Tarea original:" in texto_compacto
    # Con ventana=2 y 3 turnos completados, el T1 queda fuera de la compacta.
    assert "obtener_alertas" not in texto_compacto, "T1 debería estar fuera de la ventana"
    assert "obtener_alertas" in texto_default, "loop_default sí incluye T1"

    print("\n✅ Ejemplo 04 completado correctamente.")


if __name__ == "__main__":
    main()
