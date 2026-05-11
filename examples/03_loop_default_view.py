"""
Ejemplo 03 — La vista `loop_default`: lo que el agente realmente ve
====================================================================

Caso funcional
--------------
El `History` guarda muchas entries (prompts, respuestas, tool calls,
markers internos como `run_start`, `step_start`, etc.). Pero el modelo,
en cada turno, **no recibe el log crudo**: recibe una **representación
textual** que se arma a partir del log. A esa representación se le llama
**vista**.

La vista es una función pura `History → str | RenderedPrompt`:
- Pura: misma History, mismo output.
- Sin estado, sin side effects, sin I/O.
- Se registra en el History con un nombre.

El `InstantLoop` viene con una vista por defecto llamada `loop_default`,
que se registra automáticamente en tu History al construir el Loop. Es
la vista que el agente recibe como prompt en cada turno.

Qué muestra este ejemplo
------------------------
1. Antes de construir el Loop, el History no tiene vistas registradas.
2. Al construir el Loop, este registra `loop_default` automáticamente.
3. Después del run, ejecutamos `history.export("loop_default")` y
   miramos:
   - Qué texto exacto recibiría el modelo en el siguiente turno.
   - El shape del `RenderedPrompt` que devuelve la vista.
4. Comparamos el tamaño del log crudo vs. el texto compacto que ve el
   modelo: hay entries que la vista filtra (markers internos del
   orchestrator) y entries que renderea (prompt, response, tool_call).
5. Llamamos la vista dos veces consecutivas para mostrar que es
   determinista — función pura, no tiene memoria.

Cómo correr
-----------
    python3 examples/03_loop_default_view.py
"""
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
# RenderedPrompt vive en el sub-paquete `instantneo.loop`, no en el top-level.
from instantneo.loop import RenderedPrompt


# ────────────────────────────────────────────────────────────────────
# Tools y datos simulados (mismo dominio que los ejemplos anteriores)
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


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    # ────────────────────────────────────────────────────────────────
    # 1. History vacío, sin vistas
    # ────────────────────────────────────────────────────────────────
    # Un History recién creado no tiene ninguna vista registrada. Las
    # vistas son funciones que tú registras (o que el Loop registra por
    # ti al construirse).
    history = History(name="vista_demo")
    section("ANTES DE CONSTRUIR EL LOOP")
    print(f"  history.list_views() → {history.list_views()}")
    assert history.list_views() == []

    # ────────────────────────────────────────────────────────────────
    # 2. Construyes el Loop → se registra `loop_default` automáticamente
    # ────────────────────────────────────────────────────────────────
    # El Loop, al construirse, verifica si tu History tiene una vista
    # llamada `loop_default`. Si no la tiene, la registra. Si ya la
    # tenías (porque registraste tu propia vista custom con ese nombre,
    # o porque otro Loop sobre el mismo History ya la había registrado),
    # respeta la tuya y no la sobreescribe.
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
        name="ejemplo_03",
        stop_tool="reportar",
        max_steps=8,
    )

    section("DESPUÉS DE CONSTRUIR EL LOOP")
    print(f"  history.list_views()              → {history.list_views()}")
    print(f"  history.has_view('loop_default')  → {history.has_view('loop_default')}")
    assert history.has_view("loop_default")

    # ────────────────────────────────────────────────────────────────
    # 3. Corremos el loop
    # ────────────────────────────────────────────────────────────────
    print()
    print(">>> Ejecutando el loop...")
    result = loop.run("Revisa las alertas y emite un reporte.")
    print(f">>> Terminó: {result.terminated_reason} en {result.total_steps} steps")

    # ────────────────────────────────────────────────────────────────
    # 4. Ejecutamos la vista: lo que el modelo vería en el próximo turno
    # ────────────────────────────────────────────────────────────────
    # `history.export("loop_default")` ejecuta la función registrada
    # bajo ese nombre, pasándole el History entero. La vista devuelve un
    # `RenderedPrompt`: un dataclass con `text`, `images`, `image_detail`
    # y `stop_reason`. Si el Loop hubiera continuado, le habría pasado
    # `text` al agente como prompt del siguiente turno.
    rendered = history.export("loop_default")
    assert isinstance(rendered, RenderedPrompt)

    section("SHAPE DEL RenderedPrompt (lo que la vista devuelve)")
    print(f"  type(rendered)         → {type(rendered).__name__}")
    print(f"  rendered.text          → str ({len(rendered.text)} chars)")
    print(f"  rendered.images        → {rendered.images}")
    print(f"  rendered.image_detail  → {rendered.image_detail}")
    print(f"  rendered.stop_reason   → {rendered.stop_reason}")

    section("TEXTO QUE EL MODELO RECIBIRÍA EN EL PRÓXIMO TURNO")
    print(rendered.text)

    # ────────────────────────────────────────────────────────────────
    # 5. Comparación: log crudo vs. lo que ve el modelo
    # ────────────────────────────────────────────────────────────────
    # La vista no es un volcado del log: filtra y formatea. Entradas
    # internas del orchestrator (run_start, step_start, step_end,
    # run_end, stop_signal) NO van al modelo. Solo van las narrativas
    # (prompt, response, tool_call), agrupadas por turno.
    section("LOG CRUDO vs. VISTA")
    print(f"  total de entries en el log : {len(history.all())}")
    print(f"  entries que la vista incluye:")
    for tipo in ("prompt", "response", "tool_call"):
        n = len(history.by_type(tipo))
        if n:
            print(f"     - {tipo:11} → {n}")
    print(f"  entries internas filtradas :")
    for tipo in ("run_start", "step_start", "step_end", "stop_signal", "run_end"):
        n = len(history.by_type(tipo))
        if n:
            print(f"     - {tipo:11} → {n}")

    # ────────────────────────────────────────────────────────────────
    # 6. La vista es pura: dos ejecuciones consecutivas dan lo mismo
    # ────────────────────────────────────────────────────────────────
    # Esto es importante: la vista no tiene memoria, no se "consume",
    # no genera side effects. Puedes ejecutarla N veces y siempre te da
    # el mismo output mientras la History no cambie.
    section("DETERMINISMO — la vista es función pura")
    a = history.export("loop_default")
    b = history.export("loop_default")
    assert a.text == b.text
    assert a.images == b.images
    print("  history.export('loop_default') dos veces → mismo output ✓")

    # ────────────────────────────────────────────────────────────────
    # 7. Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    assert "## Turno 1" in rendered.text, "la vista agrupa por turno"
    assert "obtener_alertas" in rendered.text, "renderea las tool calls"
    assert "reportar" in rendered.text
    assert "run_start" not in rendered.text, "no filtra hacia adentro markers internos"

    print("\n✅ Ejemplo 03 completado correctamente.")


if __name__ == "__main__":
    main()
