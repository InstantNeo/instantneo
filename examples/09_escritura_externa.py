"""
Ejemplo 09 — Escritura arbitraria al History desde código externo
===================================================================

Caso funcional
--------------
El History no es propiedad del Loop ni del bridge. **Cualquier pieza de
tu código puede llamar `history.append(...)` y dejar una entry**. Eso
abre un patrón muy útil: insertar información de **fuentes externas**
al agente, sin que pase por el Loop ni por una tool.

Ejemplos reales del patrón:

  - Un webhook de alertas (Prometheus, Grafana, Pingdom) recibe un
    evento y lo deja como entry en el History.
  - El usuario manda un memo desde un dashboard externo: tu backend lo
    appendea al History del agente.
  - Un cron programado deja una nota de auditoría.
  - Un sistema de eventos (Kafka, RabbitMQ) consume y appendea cada
    evento relevante.

La consecuencia: el agente, en su próximo turno, ve esos eventos en su
contexto (vía la vista) y puede reaccionar a ellos sin que hayas tenido
que pedirle nada por prompt.

Qué muestra este ejemplo
------------------------
1. Tres "fuentes externas" simuladas (un memo del usuario, una alerta
   de un hook de monitoreo, una nota de auditoría) llegan **entre el
   primer y el segundo turno del usuario** y se appendean al History
   con `history.append(...)`.
2. Una vista custom detecta entries con tipos "externos"
   (`memo_usuario`, `evento_monitoreo`, `nota_auditoria`) y las
   muestra en un bloque destacado al inicio del contexto.
3. En el siguiente turno del agente operador, el agente ve esos
   eventos y los menciona/usa en su respuesta — sin que el usuario
   los haya pedido y sin que pase por una tool.

Cómo correr
-----------
    python3 examples/09_escritura_externa.py
"""
import json
import os
import sys
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
from instantneo.history.queries import current_run_id


# ────────────────────────────────────────────────────────────────────
# Tools del agente operador (mínimas — el foco está en eventos externos)
# ────────────────────────────────────────────────────────────────────
ALERTAS_ACTIVAS = [
    {"id": "A1", "tipo": "disco",   "nivel": "media"},
    {"id": "A2", "tipo": "memoria", "nivel": "crítica"},
]


@tool(description="Lista las alertas activas del sistema.", parameters={})
def obtener_alertas() -> list:
    return ALERTAS_ACTIVAS


@tool(
    description="Entrega la respuesta final al usuario y cierra el turno.",
    parameters={"mensaje": {"description": "Respuesta al usuario.", "type": "string"}},
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
# Vista del operador — muestra eventos externos como bloque destacado
# ────────────────────────────────────────────────────────────────────
# Convención del ejemplo: cualquier entry cuyo type esté en TIPOS_EXTERNOS
# se trata como "evento externo". Lo importante: el History no impone
# ningún schema — somos nosotros los que definimos la convención.
TIPOS_EXTERNOS = {"memo_usuario", "evento_monitoreo", "nota_auditoria"}


def vista_operador(history) -> str:
    rid_actual = current_run_id(history)
    ahora = time.time()

    # Eventos externos (de cualquier run, ordenados por id).
    eventos_ext = sorted(
        [e for e in history.all() if e.type in TIPOS_EXTERNOS],
        key=lambda e: e.id,
    )

    # Narrativas del operador para hilar el contexto.
    narrativas = sorted(
        [e for e in history.all()
         if e.type in ("prompt", "response", "tool_call")
         and isinstance(e.content, dict)
         and e.content.get("origin") == "loop_operador"],
        key=lambda e: e.id,
    )

    # Separar: del run actual (mensaje + trabajo) vs. previas (otros runs).
    mensaje_actual = ""
    actividad_actual, previas = [], []
    for e in narrativas:
        if e.content.get("run_id") == rid_actual:
            if e.type == "prompt":
                mensaje_actual = e.content.get("text", "")
            else:
                actividad_actual.append(e)
        else:
            previas.append(e)

    lines: list[str] = []

    # 1. Eventos externos — bloque destacado al inicio.
    if eventos_ext:
        lines.append("[Eventos externos recibidos]")
        for e in eventos_ext:
            edad = max(0, ahora - e.timestamp)
            c = e.content if isinstance(e.content, dict) else {}
            text = c.get("text", "")
            extra = ""
            if "severity" in c:
                extra = f"  [{c['severity']}]"
            lines.append(
                f"  [hace ~{edad:.0f}s] {e.author} / {e.type}{extra}: {text}"
            )
        lines.append("")

    # 2. Conversación previa (del operador).
    if previas:
        lines.append("Conversación previa:")
        for e in previas:
            c = e.content if isinstance(e.content, dict) else {}
            edad = max(0, ahora - e.timestamp)
            if e.type == "prompt":
                lines.append(f"  [hace ~{edad:.0f}s] Usuario: {c.get('text', '')}")
            elif e.type == "response":
                t = (c.get("text") or "").strip()
                if t:
                    lines.append(f"  [hace ~{edad:.0f}s] Asistente: {t}")
            elif e.type == "tool_call":
                name = c.get("name")
                args = c.get("arguments") or {}
                result = c.get("result")
                rs = json.dumps(result, ensure_ascii=False, default=str)
                if len(rs) > 200:
                    rs = rs[:200] + "..."
                lines.append(f"  [hace ~{edad:.0f}s] {name}({args}) → {rs}")
        lines.append("")

    lines.append(f"Mensaje actual del usuario: {mensaje_actual}")

    if actividad_actual:
        lines.append("")
        lines.append("Tu trabajo en este turno hasta ahora:")
        for e in actividad_actual:
            c = e.content
            name = c.get("name", "")
            args = c.get("arguments") or {}
            result = c.get("result")
            if e.type == "tool_call":
                rs = json.dumps(result, ensure_ascii=False, default=str)
                if len(rs) > 200:
                    rs = rs[:200] + "..."
                lines.append(f"  {name}({args}) → {rs}")

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────
# Simulador de fuentes externas — cualquier código puede appendear
# ────────────────────────────────────────────────────────────────────
# Estas tres funciones representan tres "sistemas" distintos. Ninguno
# sabe que existe un Loop ni un agente: cada uno solo recibe un
# History y appendea una entry. El bus de coordinación es el History.
def evento_de_dashboard_de_usuario(history: History) -> None:
    """Simula un memo dejado por el usuario en un dashboard externo."""
    history.append(
        author="user_dashboard",
        type="memo_usuario",
        content={
            "text": "Voy a estar fuera 2 horas. Si hay algo crítico, "
                    "prepárame un resumen ejecutivo.",
        },
    )


def evento_de_hook_de_monitoreo(history: History) -> None:
    """Simula un webhook de Prometheus/Grafana con una alerta nueva."""
    history.append(
        author="prometheus_hook",
        type="evento_monitoreo",
        content={
            "text": "Latencia p95 de pagos-api subió a 8200ms (normal 1500ms).",
            "servicio": "pagos-api",
            "severity": "warning",
        },
    )


def evento_de_bot_de_auditoria(history: History) -> None:
    """Simula un bot de auditoría que avisa de un reinicio programado."""
    history.append(
        author="audit_bot",
        type="nota_auditoria",
        content={
            "text": "Reinicio programado del servidor prod-app-01 en 30 min.",
            "servidor": "prod-app-01",
        },
    )


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    history = History(name="chat_con_eventos_externos")
    history.add_view("vista_operador", vista_operador)

    agente = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup=(
            "Eres un asistente conversacional de operaciones. En cada "
            "turno trabajas internamente con tus tools y al final "
            "llamas `responder(mensaje)`.\n\n"
            "Si en tu contexto aparece un bloque [Eventos externos recibidos], "
            "trátalos como información oficial llegada de otros sistemas y "
            "tenlos en cuenta en tu respuesta cuando sean relevantes."
        ),
        tools=[obtener_alertas, responder],
    )
    agente.name = "agente_operador"
    loop = InstantLoop(
        agent=agente,
        history=history,
        name="loop_operador",
        view="vista_operador",
        stop_tool="responder",
        max_steps=4,
    )

    # ────────────────────────────────────────────────────────────────
    # Turno 1: conversación normal
    # ────────────────────────────────────────────────────────────────
    section("TURNO 1 — usuario pregunta lo normal")
    r1 = loop.run("Lista las alertas activas del sistema.")
    print(f"  resultado: {r1.terminated_reason} ({r1.total_steps} steps)")

    # ────────────────────────────────────────────────────────────────
    # Entre turno 1 y 2: TRES sistemas externos appendean entries
    # ────────────────────────────────────────────────────────────────
    # El agente está dormido. Otros sistemas escriben al History
    # directamente. En el próximo turno, la vista del operador les
    # mostrará estas entries al agente.
    section("ENTRE TURNOS — fuentes externas escriben al History")
    print("  ▸ user_dashboard appendea memo_usuario")
    evento_de_dashboard_de_usuario(history)
    print("  ▸ prometheus_hook appendea evento_monitoreo")
    evento_de_hook_de_monitoreo(history)
    print("  ▸ audit_bot appendea nota_auditoria")
    evento_de_bot_de_auditoria(history)

    print(f"\n  entries totales en el History ahora: {len(history.all())}")
    print(f"  de las cuales, eventos externos    : "
          f"{sum(1 for e in history.all() if e.type in TIPOS_EXTERNOS)}")

    # ────────────────────────────────────────────────────────────────
    # Turno 2: el agente ve los eventos externos via la vista
    # ────────────────────────────────────────────────────────────────
    # No le pasamos los eventos por prompt ni por tool. Solo le pedimos
    # algo distinto. La vista los inyectará al inicio de su contexto.
    section("TURNO 2 — el agente ve los eventos externos via la vista")
    r2 = loop.run("¿Hay algo que deba tener en cuenta?")
    print(f"  resultado: {r2.terminated_reason} ({r2.total_steps} steps)")

    # ────────────────────────────────────────────────────────────────
    # Inspección: ¿qué respondió el agente en el turno 2?
    # ────────────────────────────────────────────────────────────────
    section("RESPUESTA DEL AGENTE EN EL TURNO 2")
    ultimo_responder = next(
        (tc for tc in reversed(history.by_type("tool_call"))
         if tc.content.get("name") == "responder"
         and tc.content.get("run_id") == r2.run_id),
        None,
    )
    if ultimo_responder:
        mensaje = (ultimo_responder.content.get("arguments") or {}).get("mensaje", "")
        print(f"  {mensaje}")

    # ────────────────────────────────────────────────────────────────
    # Snapshot del contexto que vio el agente en su último turno
    # ────────────────────────────────────────────────────────────────
    section("CONTEXTO QUE VIO EL AGENTE (vista_operador renderizada)")
    print(history.export("vista_operador"))

    # ────────────────────────────────────────────────────────────────
    # Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    # 3 eventos externos en el History.
    eventos_ext = [e for e in history.all() if e.type in TIPOS_EXTERNOS]
    assert len(eventos_ext) == 3
    # Tres authors distintos (uno por fuente).
    authors_ext = {e.author for e in eventos_ext}
    assert authors_ext == {"user_dashboard", "prometheus_hook", "audit_bot"}
    # El agente debería mencionar al menos uno de los eventos en su
    # respuesta final (heurística suave; el modelo es no determinista).
    if ultimo_responder:
        mensaje = (ultimo_responder.content.get("arguments") or {}).get("mensaje", "").lower()
        menciones = sum(
            kw in mensaje
            for kw in ("memo", "pagos-api", "latencia", "reinicio",
                       "auditor", "prometheus", "dashboard", "fuera 2")
        )
        assert menciones >= 1, (
            "se esperaba que el agente mencionara al menos un evento externo "
            f"en su respuesta; obtuvo: {mensaje[:200]!r}"
        )

    print("\n✅ Ejemplo 09 completado correctamente.")


if __name__ == "__main__":
    main()
