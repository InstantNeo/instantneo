"""
Ejemplo 06 — Chat con empalme temporal del History
====================================================

Caso funcional
--------------
Tienes un asistente conversacional: el usuario hace varias preguntas a
lo largo del tiempo, y entre cada pregunta el agente trabaja varios
pasos internos (consulta APIs, deduce, etc.). El History acumula todo:
los prompts del usuario, los pasos internos del agente, las respuestas
finales. Quieres que el agente **recuerde lo reciente** sin tener que
revivir toda la sesión cada vez.

La pregunta práctica: ¿qué pedazo del History le mostramos al agente
cuando arranca un nuevo turno? Hay varias políticas razonables:

  - "Solo este turno"      → la default de `loop_default` (filtra por
                              `current_run_id`). El agente no recuerda
                              nada de turnos anteriores.
  - "Toda la conversación" → `show_all_runs=True`. Memoria infinita
                              hasta que los tokens te coman vivo.
  - "Ventana temporal"     → trae lo de los últimos N segundos. Lo
                              cercano sí, lo viejo no. Es el patrón
                              típico de chatbots reales.

Este ejemplo escribe esa **ventana temporal** como vista custom, y la
compara contra la default mostrando que el agente se comporta distinto
según qué vista usa.

Qué muestra este ejemplo
------------------------
1. Una conversación de 3 turnos con la **vista default** (`loop_default`)
   sobre un History propio. El agente olvida entre turnos, así que
   reconsulta cosas que ya había consultado.
2. La misma conversación con una **vista temporal** custom sobre otro
   History limpio. El agente recuerda lo de hace pocos segundos y
   evita reconsultas.
3. Comparamos cuántas veces cada agente llamó cada tool.

Cómo correr
-----------
    python3 examples/06_chat_temporal_memory.py
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
# Tools
# ────────────────────────────────────────────────────────────────────
# Mismo dominio de alertas que en ejemplos anteriores, más una tool
# `responder` que es la que cierra cada turno del chat. Cada vez que el
# usuario pregunta algo, el agente trabaja N pasos internos y al final
# llama `responder(mensaje)`, que termina ese `loop.run()`.
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
    description=(
        "Llama esta función para entregar la respuesta final al usuario "
        "en el turno actual. Después de llamarla no sigas razonando."
    ),
    parameters={
        "mensaje": {
            "description": "Respuesta dirigida al usuario.",
            "type": "string",
        },
    },
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
# Vista custom: empalme por timestamp
# ────────────────────────────────────────────────────────────────────
# Mismo patrón que el 04: factory que captura `ventana_segundos` en
# closure y devuelve la callable que el History ejecuta.
#
# La vista produce TRES bloques en el texto que recibe el agente:
#
#   1. Conversación previa: entries narrativas de OTROS runs cuyo
#      timestamp esté dentro de la ventana hacia atrás. Es la "memoria"
#      entre turnos del chat.
#   2. Mensaje actual del usuario (prompt del run en curso).
#   3. Tu trabajo en este turno: entries del run actual (lo que el
#      agente ya hizo en sus steps anteriores dentro del mismo turno).
#
# Si omites el bloque 3, el agente repite la misma tool una y otra vez
# porque cada step lo recibiría como "primer step". Es exactamente el
# trabajo que hace `loop_default` por dentro: mostrar el progreso del
# run actual. Acá lo agregamos explícitamente.
#
# El umbral hacia atrás es ahora - ventana_segundos. Como `Entry.timestamp`
# se asigna en `append`, los runs muy viejos quedan fuera automáticamente.
def crear_vista_temporal(ventana_segundos: float = 300.0):
    def _render_entry(e, ahora: float) -> str:
        c = e.content if isinstance(e.content, dict) else {}
        edad = max(0, ahora - e.timestamp)
        if e.type == "prompt":
            return f"  [hace ~{edad:.0f}s] Usuario: {c.get('text', '')}"
        if e.type == "response":
            text = (c.get("text") or "").strip()
            return f"  [hace ~{edad:.0f}s] Agente: {text}" if text else ""
        if e.type == "tool_call":
            name = c.get("name")
            args = c.get("arguments") or {}
            result = c.get("result")
            rs = json.dumps(result, ensure_ascii=False, default=str)
            if len(rs) > 180:
                rs = rs[:180] + "..."
            return f"  [hace ~{edad:.0f}s] {name}({args}) → {rs}"
        return ""

    def vista_temporal(history) -> str:
        rid_actual = current_run_id(history)
        ahora = time.time()
        cutoff = ahora - ventana_segundos

        # Mensaje actual del usuario (prompt del run en curso).
        prompts_actuales = [
            e for e in history.by_type("prompt")
            if isinstance(e.content, dict) and e.content.get("run_id") == rid_actual
        ]
        mensaje_actual = (
            prompts_actuales[0].content.get("text", "")
            if prompts_actuales else ""
        )

        # Conversación previa (otros runs dentro de la ventana).
        previas, actividad_actual = [], []
        for e in history.all():
            if e.type not in ("prompt", "response", "tool_call"):
                continue
            c = e.content if isinstance(e.content, dict) else {}
            if c.get("run_id") == rid_actual:
                # No incluir el prompt del run actual acá: ya lo
                # mostramos como "Mensaje actual". Sí incluir
                # response/tool_call → es el progreso interno del turno.
                if e.type != "prompt":
                    actividad_actual.append(e)
            elif e.timestamp >= cutoff:
                previas.append(e)
        previas.sort(key=lambda e: e.id)
        actividad_actual.sort(key=lambda e: e.id)

        # Render: previas → mensaje actual → actividad propia.
        lines: list[str] = []
        if previas:
            lines.append(f"Conversación previa (últimos {int(ventana_segundos)}s):")
            for e in previas:
                r = _render_entry(e, ahora)
                if r:
                    lines.append(r)
            lines.append("")
        else:
            lines.append(
                "(Conversación nueva. No hay turnos previos dentro de "
                f"la ventana de {int(ventana_segundos)}s.)"
            )
            lines.append("")

        lines.append(f"Mensaje actual del usuario: {mensaje_actual}")

        if actividad_actual:
            lines.append("")
            lines.append("Tu trabajo en este turno hasta ahora:")
            for e in actividad_actual:
                r = _render_entry(e, ahora)
                if r:
                    lines.append(r)

        return "\n".join(lines)

    return vista_temporal


# ────────────────────────────────────────────────────────────────────
# Conversación: los tres "mensajes del usuario"
# ────────────────────────────────────────────────────────────────────
# La conversación está armada para que el run 2 dependa de info que el
# run 1 ya obtuvo (la lista de alertas). Eso revela si el agente
# recuerda o no.
CONVERSACION = [
    "Lista las alertas activas del sistema.",
    "Dame el detalle de la más crítica.",
    "Genera un reporte con la acción recomendada y el ID de la alerta crítica.",
]


def construir_agente() -> InstantNeo:
    """El mismo agente en ambas secciones: cambia solo la vista."""
    return InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup=(
            "Eres un asistente conversacional de operaciones. En cada "
            "turno trabajas internamente con las tools que necesites y "
            "al final llamas la tool `responder` con un mensaje claro "
            "para el usuario.\n\n"
            "Importante: si en la conversación previa ya consultaste algo, "
            "no lo vuelvas a consultar — reutiliza la información."
        ),
        tools=[obtener_alertas, obtener_detalle_alerta, responder],
    )


def correr_chat(history: History, view_name: str) -> list:
    """Corre la misma conversación de 3 turnos sobre el History dado,
    usando la vista indicada. Devuelve la lista de RunResults."""
    agent = construir_agente()
    loop = InstantLoop(
        agent=agent,
        history=history,
        name=f"chat_{view_name}",
        view=view_name,
        stop_tool="responder",
        max_steps=6,
    )
    resultados = []
    for prompt in CONVERSACION:
        r = loop.run(prompt)
        resultados.append(r)
    return resultados


def contar_tool_calls(history: History) -> dict:
    """Cuenta cuántas veces se llamó cada tool en el History."""
    counts: dict[str, int] = {}
    for e in history.by_type("tool_call"):
        name = e.content.get("name") if isinstance(e.content, dict) else None
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    # ────────────────────────────────────────────────────────────────
    # SECCIÓN A — Conversación con la vista default (sin memoria entre turnos)
    # ────────────────────────────────────────────────────────────────
    # Con `loop_default` cada run solo ve su propio run_id. El agente
    # arranca cada turno "ciego" respecto a los anteriores.
    section("SECCIÓN A — vista loop_default (sin memoria entre turnos)")
    history_a = History(name="chat_default")
    print(">>> Ejecutando 3 turnos del chat con loop_default...")
    resultados_a = correr_chat(history_a, "loop_default")
    for i, r in enumerate(resultados_a, start=1):
        print(f"  turno {i}: {r.terminated_reason} en {r.total_steps} steps")

    # ────────────────────────────────────────────────────────────────
    # SECCIÓN B — Conversación con la vista temporal (memoria de últimos 300s)
    # ────────────────────────────────────────────────────────────────
    # Mismo agente, mismo prompt, History nuevo (limpio). Solo cambia la
    # vista. Registramos la vista en el History ANTES de construir el
    # Loop — si no, el Loop crashea con LoopConfigError.
    section("SECCIÓN B — vista temporal (recuerda últimos 300s)")
    history_b = History(name="chat_temporal")
    history_b.add_view("temporal", crear_vista_temporal(ventana_segundos=300))
    print(">>> Ejecutando 3 turnos del chat con la vista temporal...")
    resultados_b = correr_chat(history_b, "temporal")
    for i, r in enumerate(resultados_b, start=1):
        print(f"  turno {i}: {r.terminated_reason} en {r.total_steps} steps")

    # ────────────────────────────────────────────────────────────────
    # Comparación: ¿cuántas tools llamó cada agente?
    # ────────────────────────────────────────────────────────────────
    # La métrica clave es `obtener_alertas`. Con vista default, el
    # agente la llama en cada turno donde la necesita (≥ 2 veces típico).
    # Con vista temporal, la llama 1 sola vez en el turno 1 — los
    # turnos 2 y 3 leen la respuesta del primer turno desde la vista.
    section("COMPARACIÓN: llamadas a tools por sección")
    counts_a = contar_tool_calls(history_a)
    counts_b = contar_tool_calls(history_b)
    todas = sorted(set(counts_a) | set(counts_b))
    print(f"  {'tool':<26} {'default':>10} {'temporal':>10}")
    print(f"  {'-' * 26} {'-' * 10} {'-' * 10}")
    for tool_name in todas:
        a = counts_a.get(tool_name, 0)
        b = counts_b.get(tool_name, 0)
        print(f"  {tool_name:<26} {a:>10} {b:>10}")

    # ────────────────────────────────────────────────────────────────
    # Vista renderizada después del turno 3 (sección B)
    # ────────────────────────────────────────────────────────────────
    # Para que veas qué texto exacto generaba la vista temporal en cada
    # turno del chat, imprimimos lo que devolvería ahora (después del
    # último turno). Sirve como muestra de cómo el agente "veía" su
    # contexto al arrancar el siguiente turno hipotético.
    section("VISTA TEMPORAL — render actual (sección B)")
    texto = history_b.export("temporal")
    print(texto)

    # ────────────────────────────────────────────────────────────────
    # Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    # Estas asunciones pueden fallar con cierta probabilidad porque el
    # modelo no es determinista. El patrón observado en pruebas es
    # consistente, pero si fallara, lee el conteo arriba para ver qué
    # pasó.
    assert all(r.terminated_reason == "stop_signal" for r in resultados_a)
    assert all(r.terminated_reason == "stop_signal" for r in resultados_b)
    assert counts_b.get("obtener_alertas", 0) <= counts_a.get("obtener_alertas", 0), (
        "se esperaba que la vista temporal redujera reconsultas de obtener_alertas"
    )

    print("\n✅ Ejemplo 06 completado correctamente.")


if __name__ == "__main__":
    main()
