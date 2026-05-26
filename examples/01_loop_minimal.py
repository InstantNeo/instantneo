"""
Ejemplo 01 — Un agente corriendo en loop, lo más simple posible
================================================================

Caso funcional
--------------
Tienes un agente al que le pides una tarea que **no se resuelve en una
sola respuesta del LLM**. El agente necesita consultar información,
decidir qué hacer con ella, quizás profundizar, y recién entonces emitir
un reporte final. En otras palabras: tiene que **trabajar en varios
turnos**, no en uno.

Eso es lo que hace `InstantLoop`: envuelve un `InstantNeo` y lo corre N
veces, acumulando contexto entre turnos, hasta que se dispare alguna
condición de parada.

La forma más simple de pararlo: darle una **tool de cierre**. Cuando el
agente la llama, el loop entiende "ya está, terminó" y se detiene. El
nombre de esa tool lo eliges tú: puede ser `reportar`, `finalizar`,
`entregar_resultado`, lo que tenga sentido en tu dominio. Acá usamos
`reportar` para enfatizar que es cualquier tool — no hay un nombre
especial reservado por la librería.

Qué muestra este ejemplo
------------------------
Simulamos un caso típico: el agente revisa alertas de un sistema,
identifica la más crítica, consulta su detalle, y emite un reporte con
una acción recomendada. La tarea está armada para que el agente
**necesite** múltiples turnos: no puede pedir el detalle de una alerta
sin saber primero el ID, y no puede reportar sin haber leído el detalle.

Pasos:
1. Definimos tres tools: `obtener_alertas`, `obtener_detalle_alerta`,
   `reportar`.
2. Creamos un `InstantNeo` con esas tools.
3. Lo envolvemos en un `InstantLoop` con `stop_tool="reportar"`.
4. Corremos: `loop.run("...")`.
5. Inspeccionamos qué pasó en el `RunResult` y en el `History`.

Lo que pasa con el History (sin que lo hayas pedido)
----------------------------------------------------
Aunque no lo pasaste por argumento, **el loop creó un `History` propio**
y lo fue alimentando turno a turno. Cada cosa que ocurrió quedó guardada
como una `Entry` inmutable, en orden: el prompt inicial, las respuestas
del agente, las tool calls con sus resultados, los marcadores de inicio
y fin de cada step.

Al final del run puedes leer `result.history` y reconstruir todo lo que
pasó. En ejemplos posteriores vamos a desacoplar ese History — crearlo
afuera, pasarlo a varios loops, registrarle vistas. Por ahora alcanza
con saber que está ahí y que es la fuente de verdad del run.

Requisitos
----------
- `.env` con `OPEN_AI_API_KEY` en la raíz del repo.
- Modelo por default: `gpt-4.1-mini` (chat model, sin reasoning interno).
  Si quieres usar un modelo reasoning como `gpt-5-mini`, acuérdate de
  subir `max_tokens` en el agente (ej. 2048 o más) para que tenga budget
  tanto para pensar como para emitir respuesta y tool calls.

Cómo correr
-----------
    python3 examples/01_loop_minimal.py
"""
import os
import sys
from pathlib import Path

# El worktree puede tener una versión vieja de instantneo instalada en
# site-packages; insertamos la raíz del repo en sys.path para usar el código
# local, no el del paquete instalado.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Cargamos .env si está disponible (`pip install python-dotenv` si no lo está).
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env", override=True)
except ImportError:
    pass

from instantneo import InstantNeo, InstantLoop, tool


# ────────────────────────────────────────────────────────────────────
# 1. Tools del agente
# ────────────────────────────────────────────────────────────────────
# Tres funciones decoradas con `@tool`. El decorador convierte cada una
# en algo que InstantNeo sabe describir al modelo (nombre, descripción,
# parámetros). El cuerpo se ejecuta cuando el modelo llama a la tool.
#
# Las dos primeras simulan acceso a un sistema de monitoreo. La tercera,
# `reportar`, es la que va a cerrar el loop.

ALERTAS_ACTIVAS = [
    {"id": "A1", "tipo": "disco",   "nivel": "media"},
    {"id": "A2", "tipo": "memoria", "nivel": "crítica"},
    {"id": "A3", "tipo": "red",     "nivel": "baja"},
]

DETALLES_ALERTAS = {
    "A1": "Disco al 78% en /var. Crecimiento sostenido en las últimas 12 horas.",
    "A2": "Uso de memoria al 95% en el servidor de aplicaciones. Procesos potencialmente colgados.",
    "A3": "Latencia de red de 250ms hacia el data center secundario.",
}


@tool(
    description="Devuelve la lista de alertas activas del sistema, con su ID, tipo y nivel.",
    parameters={},
)
def obtener_alertas() -> list:
    return ALERTAS_ACTIVAS


@tool(
    description="Devuelve la descripción detallada de una alerta a partir de su ID.",
    parameters={
        "alerta_id": {
            "description": "ID de la alerta a consultar (ej. 'A2').",
            "type": "string",
        },
    },
)
def obtener_detalle_alerta(alerta_id: str) -> dict:
    return {
        "id": alerta_id,
        "descripcion": DETALLES_ALERTAS.get(alerta_id, "Alerta no encontrada."),
    }


# Esta es la tool que cierra el loop. El nombre `reportar` no tiene nada
# de especial — podría llamarse `finalizar`, `entregar_resultado`, etc.
# Lo único que importa es que se lo declares al loop como `stop_tool=...`.
@tool(
    description="Llama esta función cuando hayas terminado el análisis y tengas un reporte final.",
    parameters={
        "alerta_critica_id": {
            "description": "ID de la alerta identificada como más crítica.",
            "type": "string",
        },
        "resumen": {
            "description": "Resumen del análisis en una o dos oraciones.",
            "type": "string",
        },
        "accion_recomendada": {
            "description": "Próxima acción concreta a tomar.",
            "type": "string",
        },
    },
)
def reportar(alerta_critica_id: str, resumen: str, accion_recomendada: str) -> dict:
    return {
        "alerta_critica_id": alerta_critica_id,
        "resumen": resumen,
        "accion_recomendada": accion_recomendada,
    }


# ────────────────────────────────────────────────────────────────────
# 2. Configuración del agente
# ────────────────────────────────────────────────────────────────────
PROVIDER = "openai"
MODEL = "gpt-4.1-mini"
API_KEY = os.environ.get("OPEN_AI_API_KEY")

if not API_KEY:
    print("ERROR: no encontré OPEN_AI_API_KEY en el entorno.")
    print("       Configura el .env del repo o exporta la variable.")
    sys.exit(1)


def main() -> None:
    # ────────────────────────────────────────────────────────────────
    # 3. Agente
    # ────────────────────────────────────────────────────────────────
    # El `role_setup` define la identidad y las reglas de operación
    # del agente. En ejemplos posteriores vamos a mover las
    # instrucciones operativas a `AgentCapabilities.global_instructions`
    # (un mecanismo más limpio para casos reales); por ahora, todo junto.
    agent = InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup=(
            "Eres un asistente de operaciones. Tu tarea es revisar alertas "
            "del sistema y decidir cuál priorizar.\n\n"
            "Flujo de trabajo:\n"
            "1. Llama a `obtener_alertas` para ver la lista activa.\n"
            "2. Identifica la más crítica y llama a `obtener_detalle_alerta` con su ID.\n"
            "3. Cuando tengas el detalle, llama a `reportar` con un resumen y "
            "una acción recomendada concreta.\n\n"
            "No respondas en texto plano; usa siempre las tools."
        ),
        tools=[obtener_alertas, obtener_detalle_alerta, reportar],
    )

    # ────────────────────────────────────────────────────────────────
    # 4. Loop
    # ────────────────────────────────────────────────────────────────
    # `stop_tool="reportar"` es azúcar sintáctica: por debajo, el loop
    # arma una regla en su Monitor interno que dice "si la última
    # tool_call del agente fue `reportar`, emite un stop_signal". Cuando
    # ese signal aparece en el history, el loop corta.
    #
    # `max_steps=8` es un techo defensivo por si el agente se traba.
    loop = InstantLoop(
        agent=agent,
        name="ejemplo_01",
        stop_tool="reportar",
        max_steps=8,
    )

    # ────────────────────────────────────────────────────────────────
    # 5. Corremos
    # ────────────────────────────────────────────────────────────────
    pregunta = "Revisa las alertas del sistema y emite un reporte con la acción recomendada."
    print(f"\n>>> Tarea: {pregunta}\n")

    result = loop.run(pregunta)

    # ────────────────────────────────────────────────────────────────
    # 6. Inspeccionamos el RunResult
    # ────────────────────────────────────────────────────────────────
    # `result` es un `RunResult` con metadata del run y un puntero al
    # history que se acaba de construir.
    print("─" * 60)
    print("RESULTADO DEL RUN")
    print("─" * 60)
    print(f"terminated_reason : {result.terminated_reason}")
    print(f"stop_reason       : {result.stop_reason}")
    print(f"total_steps       : {result.total_steps}")
    print(f"duration_s        : {result.duration_s:.2f}")

    # ────────────────────────────────────────────────────────────────
    # 7. Inspeccionamos el History
    # ────────────────────────────────────────────────────────────────
    # Cada acción del run quedó como una Entry en orden cronológico.
    # Algunas las emitió el orchestrator (markers: `run_start`,
    # `step_start`, `step_end`, `run_end`, `stop_signal`); otras vienen
    # del bridge que tradujo el `RunInfo` del agente a entries
    # (`response`, `tool_call`).
    history = result.history
    print()
    print("─" * 60)
    print(f"HISTORY: {len(history.all())} entries")
    print("─" * 60)
    by_type: dict[str, int] = {}
    for entry in history.all():
        by_type[entry.type] = by_type.get(entry.type, 0) + 1
    for entry_type, count in sorted(by_type.items()):
        print(f"  {entry_type:14} → {count}")

    # Detalle de las tool calls — la traza más útil para entender qué
    # decidió el agente turno a turno.
    print()
    print("─" * 60)
    print("TOOL CALLS")
    print("─" * 60)
    for tc in history.by_type("tool_call"):
        name = tc.content.get("name")
        args = tc.content.get("arguments")
        print(f"  step {tc.content.get('turn_num')}: {name}({args})")

    # ────────────────────────────────────────────────────────────────
    # 8. Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    assert result.terminated_reason == "stop_signal"
    assert any(tc.content.get("name") == "reportar" for tc in history.by_type("tool_call"))

    print("\n✅ Run completado correctamente.")


if __name__ == "__main__":
    main()
