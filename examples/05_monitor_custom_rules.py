"""
Ejemplo 05 — Monitor con reglas custom
========================================

Caso funcional
--------------
En los ejemplos anteriores usaste `stop_tool="reportar"` para parar el
loop. Eso es azúcar sintáctica que oculta un mecanismo más general: el
**Monitor**, un rule engine que observa el History y reacciona.

Un Monitor tiene reglas. Cada regla es un par `(cuándo, qué hacer)`:

    cuándo  : Callable[[History], bool]   — condición
    qué hacer : Callable[[History], None] — acción

El Loop ejecuta el Monitor después de cada step. Si la condición da
True, dispara la acción. La acción puede hacer cualquier cosa: notificar
a un sistema externo, escribir un log, enviar un email, appendear una
entry al mismo History (para auditoría), o emitir un `stop_signal` para
terminar el loop.

Este ejemplo muestra las dos categorías típicas de regla:

1. **Side effect** que NO termina el loop. La condición detecta cuando
   se llamó cierta tool; la acción manda una notificación a un destino
   externo (acá simulado con una lista en memoria) y deja rastro en el
   History.
2. **Stop**. La condición detecta cuando se llamó la tool de cierre; la
   acción emite un `stop_signal` que el Loop sabe interpretar para
   terminar. (Esto es exactamente lo que hace `stop_tool="reportar"`
   por dentro — acá lo escribimos manual para que veas el mecanismo.)

Lo importante: las dos reglas conviven en el mismo Monitor. Una dispara
en el turno 2, la otra en el turno 3. El Monitor las evalúa en orden y
ejecuta las acciones cuya condición sea True en ese momento.

Cómo correr
-----------
    python3 examples/05_monitor_custom_rules.py
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

from instantneo import History, InstantLoop, InstantNeo, Monitor, tool
# Built-ins del Monitor:
#   - `when_last_tool_called(name)` : condition factory.
#   - `stop_signal(text)`           : action factory (emite la entry que
#                                     el Loop interpreta como "termina").
from instantneo.monitor.conditions import when_last_tool_called
from instantneo.monitor.actions import stop_signal


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
# Sistema externo simulado: lista donde "se envían" notificaciones
# ────────────────────────────────────────────────────────────────────
# En un caso real podría ser un POST a Slack, un email, una llamada a
# un webhook, un push a una cola, etc. Acá lo dejamos como lista en
# memoria para no depender de servicios externos.
NOTIFICACIONES_ENVIADAS: list[str] = []


# ────────────────────────────────────────────────────────────────────
# Acción custom: notifica a un sistema externo y deja rastro en el History
# ────────────────────────────────────────────────────────────────────
# Una acción es `Callable[[History], None]`. Recibe el History (puede
# leerlo y appendearle entries) y no devuelve nada. Acá hacemos dos
# cosas:
#   1. Side effect externo: append a NOTIFICACIONES_ENVIADAS.
#   2. Side effect interno: dejar una entry en el History para
#      auditoría (cualquiera que lea el log después sabe que se notificó).
def notificar_detalle_consultado(history: History) -> None:
    # Buscamos la última tool_call para leer su result. Por la condición
    # de la regla, sabemos que es de tipo `obtener_detalle_alerta`.
    ultima_tc = next(
        (e for e in reversed(history.all()) if e.type == "tool_call"),
        None,
    )
    if ultima_tc is None:
        return
    result = ultima_tc.content.get("result") or {}
    descripcion = result.get("descripcion", "(sin descripción)")
    alerta_id = result.get("id", "?")

    # 1. Notificación externa (simulada).
    mensaje = f"[OPS] Detalle consultado para {alerta_id}: {descripcion}"
    NOTIFICACIONES_ENVIADAS.append(mensaje)

    # 2. Auditoría en el History. El `type` libre permite que cualquier
    #    consumidor downstream (otra vista, otro monitor, una query)
    #    sepa que la notificación se envió.
    history.append(
        author="monitor",
        type="notification_sent",
        content={"channel": "ops_simulado", "alerta_id": alerta_id, "message": mensaje},
    )


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    # ────────────────────────────────────────────────────────────────
    # 1. Armamos el Monitor con las dos reglas
    # ────────────────────────────────────────────────────────────────
    # El Monitor se construye vacío y le agregas reglas con `add_rule`.
    # El orden de agregado define el orden de evaluación cuando el Loop
    # lo invoca después de cada step.
    monitor = Monitor(name="ops_monitor")

    # Regla 1: side effect — notificar y auditar cuando el agente
    # consulta el detalle de una alerta.
    monitor.add_rule(
        when_last_tool_called("obtener_detalle_alerta"),
        notificar_detalle_consultado,
    )

    # Regla 2: stop — emitir stop_signal cuando el agente llama
    # `reportar`. Esto es equivalente a `stop_tool="reportar"` en el
    # constructor del Loop, pero acá lo declaramos a mano para que veas
    # el mecanismo. El text del signal tiene que coincidir con el que
    # el Loop espera en `stop_signals`.
    SIGNAL_TEXT = "agent called reportar"
    monitor.add_rule(
        when_last_tool_called("reportar"),
        stop_signal(SIGNAL_TEXT),
    )

    # ────────────────────────────────────────────────────────────────
    # 2. Agente + Loop con el Monitor custom
    # ────────────────────────────────────────────────────────────────
    # Notar que NO pasamos `stop_tool=...` — pasamos `monitors=` y
    # `stop_signals=` para que el Loop sepa qué texto cuenta como
    # señal de parada.
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
        name="ejemplo_05",
        monitors=monitor,             # ← le pasamos nuestro Monitor
        stop_signals=[SIGNAL_TEXT],   # ← le decimos qué texto significa "para"
        max_steps=8,
    )

    # ────────────────────────────────────────────────────────────────
    # 3. Corremos
    # ────────────────────────────────────────────────────────────────
    print(">>> Ejecutando el loop con Monitor custom...")
    result = loop.run("Revisa las alertas y emite un reporte.")
    print(f">>> Terminó: {result.terminated_reason} en {result.total_steps} steps")
    print(f">>> stop_reason: {result.stop_reason}")

    # ────────────────────────────────────────────────────────────────
    # 4. Efectos de la regla 1 (side effect)
    # ────────────────────────────────────────────────────────────────
    # La acción `notificar_detalle_consultado` se disparó cuando el
    # agente llamó `obtener_detalle_alerta` (paso 2). Verificamos los
    # dos efectos: la lista externa y la entry de auditoría.
    section("EFECTOS DE LA REGLA 1 (side effect)")
    print(f"  NOTIFICACIONES_ENVIADAS ({len(NOTIFICACIONES_ENVIADAS)}):")
    for n in NOTIFICACIONES_ENVIADAS:
        print(f"    - {n}")

    notification_entries = result.history.by_type("notification_sent")
    print(f"\n  entries 'notification_sent' en el History ({len(notification_entries)}):")
    for e in notification_entries:
        print(f"    - id={e.id} author={e.author!r} content={e.content}")

    # ────────────────────────────────────────────────────────────────
    # 5. Efectos de la regla 2 (stop)
    # ────────────────────────────────────────────────────────────────
    # La acción `stop_signal(...)` appendeó una entry de tipo
    # `stop_signal` cuando el agente llamó `reportar`. El Loop la
    # detectó al final del step y terminó.
    section("EFECTOS DE LA REGLA 2 (stop)")
    stop_entries = result.history.by_type("stop_signal")
    for e in stop_entries:
        print(f"  stop_signal entry: id={e.id} content.text={e.content.get('text')!r}")
    print(f"  terminated_reason: {result.terminated_reason}")
    print(f"  stop_reason: {result.stop_reason}")

    # ────────────────────────────────────────────────────────────────
    # 6. Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    assert result.terminated_reason == "stop_signal"
    assert result.stop_reason == SIGNAL_TEXT
    assert len(NOTIFICACIONES_ENVIADAS) >= 1, "regla 1 debería haber disparado"
    assert len(notification_entries) == len(NOTIFICACIONES_ENVIADAS), \
        "cada notificación externa debería tener su entry de auditoría"

    print("\n✅ Ejemplo 05 completado correctamente.")


if __name__ == "__main__":
    main()
