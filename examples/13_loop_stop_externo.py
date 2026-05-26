"""
Ejemplo 13 — Cancelación externa del Loop: `loop.stop()`
==========================================================

Caso funcional
--------------
Tienes un Loop corriendo, posiblemente en una tarea larga, y en algún
momento algo externo decide que debe parar: un timeout, un humano que
hace click en "cancelar", un watchdog que detecta que el agente
debería ceder el turno, otro sistema que invalida la consulta.

`InstantLoop` expone el método `loop.stop(reason)` para esto. Lo
podés llamar desde **cualquier thread** mientras el `loop.run()`
principal está en curso. El Loop setea un flag interno y, al final
del step actual, rompe con `terminated_reason="external"` y
`stop_reason=reason`. No interrumpe a mitad de un step (no aborta el
agente ni cancela tools en ejecución) — espera el cierre limpio del
step y termina ahí.

Qué muestra este ejemplo
------------------------
1. Un agente que monitorea el estado del sistema en bucle, sin tool
   de cierre — sería capaz de seguir indefinidamente.
2. Un thread `watchdog` que espera N segundos y luego invoca
   `loop.stop(reason="...")`.
3. El loop termina con `terminated_reason="external"`, habiendo
   completado los steps que alcanzó hasta ese momento.

Cómo correr
-----------
    python3 examples/13_loop_stop_externo.py
"""
import datetime
import os
import random
import sys
import threading
import time
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


# ────────────────────────────────────────────────────────────────────
# Tool: consulta de estado del sistema (devuelve algo distinto cada vez)
# ────────────────────────────────────────────────────────────────────
# El agente la llamará en cada step. El loop sigue iterando hasta que
# algo externo dispare el stop — ese "algo" es el watchdog más abajo.
@tool(
    description=(
        "Consulta el estado actual del sistema y devuelve métricas "
        "instantáneas: alertas activas, load average, hora UTC."
    ),
    parameters={},
)
def consultar_estado() -> dict:
    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "alertas_activas": random.randint(0, 5),
        "load_avg": round(random.uniform(0.2, 1.5), 2),
    }


PROVIDER = "openai"
MODEL = "gpt-4.1-mini"
API_KEY = os.environ.get("OPEN_AI_API_KEY")

if not API_KEY:
    print("ERROR: falta OPEN_AI_API_KEY en el entorno.")
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────
# Watchdog: thread que dispara loop.stop() después de N segundos
# ────────────────────────────────────────────────────────────────────
# El método `loop.stop(reason)` es thread-safe: setea un flag interno
# que el loop principal lee al final de cada step. No hace falta
# coordinar más nada.
def watchdog(loop: InstantLoop, segundos: float, reason: str) -> None:
    print(f"[watchdog] esperando {segundos}s antes de disparar loop.stop()")
    time.sleep(segundos)
    print(f"[watchdog] disparando loop.stop(reason={reason!r})")
    loop.stop(reason)


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    history = History(name="monitoreo_continuo")

    agente = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup=(
            "Eres un agente de monitoreo. En cada turno llamas a "
            "`consultar_estado` y emites una nota breve sobre los datos "
            "obtenidos. NO termines por tu cuenta — un sistema externo "
            "te indicará cuándo parar."
        ),
        tools=[consultar_estado],
    )
    agente.name = "agente_monitor"

    # Loop SIN stop_tool: no hay forma de que el agente lo termine.
    # El cap es max_steps (techo defensivo) o `loop.stop()` externo.
    loop = InstantLoop(
        agent=agente,
        history=history,
        name="loop_monitor",
        max_steps=15,
    )

    # Lanzamos el watchdog en un thread aparte. `daemon=True` hace que
    # no impida la salida del proceso si algo sale mal.
    SEGUNDOS_HASTA_STOP = 6.0
    RAZON_STOP = "watchdog: tiempo de monitoreo cumplido"
    t = threading.Thread(
        target=watchdog,
        args=(loop, SEGUNDOS_HASTA_STOP, RAZON_STOP),
        daemon=True,
    )
    t.start()

    section("EJECUTANDO LOOP — el watchdog disparará stop en ~6s")
    inicio = time.time()
    result = loop.run(
        "Empieza a monitorear el sistema. Reporta el estado en cada turno."
    )
    elapsed = time.time() - inicio

    # ────────────────────────────────────────────────────────────────
    # Resultado: terminado externamente
    # ────────────────────────────────────────────────────────────────
    section("RESULTADO")
    print(f"  terminated_reason : {result.terminated_reason}")
    print(f"  stop_reason       : {result.stop_reason}")
    print(f"  total_steps       : {result.total_steps}")
    print(f"  duration_s        : {result.duration_s:.2f}")
    print(f"  tiempo real total : {elapsed:.2f}s "
          f"(watchdog programado para {SEGUNDOS_HASTA_STOP}s)")

    # ────────────────────────────────────────────────────────────────
    # Inspección: ¿qué hizo el agente antes de ser detenido?
    # ────────────────────────────────────────────────────────────────
    section("ACTIVIDAD DEL AGENTE")
    consultas = history.by_type("tool_call")
    print(f"  llamadas a consultar_estado: {len(consultas)}")
    for tc in consultas[:5]:
        result_val = tc.content.get("result") or {}
        print(f"    step {tc.content.get('turn_num')}: "
              f"alertas={result_val.get('alertas_activas')}, "
              f"load={result_val.get('load_avg')}")
    if len(consultas) > 5:
        print(f"    ... y {len(consultas) - 5} más")

    # ────────────────────────────────────────────────────────────────
    # Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    assert result.terminated_reason == "external", (
        f"se esperaba terminación externa; obtuvo {result.terminated_reason!r}"
    )
    assert result.stop_reason == RAZON_STOP
    # Le dimos tiempo suficiente para hacer al menos 1 step antes de stop.
    assert result.total_steps >= 1
    # El watchdog disparó en ~6s, no debería haber tomado mucho más.
    assert elapsed < SEGUNDOS_HASTA_STOP + 20.0

    print("\n✅ Ejemplo 13 completado correctamente.")


if __name__ == "__main__":
    main()
