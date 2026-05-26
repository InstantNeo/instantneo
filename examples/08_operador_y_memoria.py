"""
Ejemplo 08 — Agente operador + agente memoria (rolling summary)
=================================================================

Caso funcional
--------------
Las conversaciones largas explotan el context window. Solución
elegante: un agente de fondo que **resume** los turnos viejos cuando se
acumulan, sustituyéndolos por una versión condensada. El agente operador
ve siempre lo mismo: el último resumen + los turnos frescos posteriores.
Es ventana deslizante con compresión, no descarte: nada se pierde, se
condensa.

El patrón:

  - **Agente operador** (envuelto en un `InstantLoop`): conversa con el
    usuario. Cada `loop.run(prompt)` es un turno del usuario. Tiene una
    vista que renderea: último `summary` (si existe) + actividad
    posterior.
  - **Agente memoria** (un `InstantNeo` directo, SIN Loop): vive
    aparte. NO recibe prompts del usuario. Se invoca **únicamente**
    cuando un Monitor del operador lo dispara. Recibe un bloque
    textual con los turnos viejos y lo condensa.

Por qué el agente memoria NO va en un Loop
-------------------------------------------
La acción `comprimir_memoria` del Monitor invoca al agente memoria
para producir el resumen. Si envolviéramos al agente memoria en un
Loop sobre el mismo History, ese loop appendearía sus propias
entries (`run_start`, `step_start`, `tool_call`, etc.) y la última
tool_call del History dejaría de ser `responder` del operador — eso
**rompería el sugar `stop_tool="responder"`** del operador, porque su
condición evalúa "la última tool_call".

La solución limpia: invocar al agente memoria como
``agente_memoria.run(prompt)`` directo. Un agente solo NO toca el
History compartido. Ejecuta el LLM call, ejecuta sus tools
internamente, y deja todo en `agent.last_run`. Después nuestra acción
lee `last_run.tool_executions`, extrae el texto, y appendea UNA sola
entry `summary` al History. Limpio y compatible con el sugar.

Trigger del agente memoria
--------------------------
El Monitor del operador tiene una regla custom con dos criterios. La
acción dispara cuando se cumple **alguno** de:

  - Han pasado N turnos desde el último summary (acá N=3).
  - El tamaño del prompt rendereado por la vista del operador supera
    M chars (acá M=5000, ~1250 tokens).

Esto desbloquea conversaciones arbitrariamente largas sin que el prompt
crezca sin tope.

Lo que el dev aprende
---------------------
1. Un Monitor no solo termina loops; también **dispara trabajo**
   arbitrario — en este caso, invocar a otro agente especialista.
2. Cuando una acción de Monitor invoca otro agente, hay una decisión
   clave: ¿el otro agente toca el mismo History? Si sí, hay que
   pensar en orden de reglas; si no (`agent.run()` directo), todo
   queda limpio. Acá usamos lo segundo.
3. Vistas que adaptan su render según presencia de ciertas entries
   (`summary`) — patrón muy poderoso de "presence-based rendering".
4. El agente memoria es solo un `InstantNeo`. No necesita ser un
   Loop para invocarse desde una acción del Monitor.

Cómo correr
-----------
    python3 examples/08_operador_y_memoria.py
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

from instantneo import History, InstantLoop, InstantNeo, Monitor, tool
from instantneo.history.queries import current_run_id


# ────────────────────────────────────────────────────────────────────
# Constantes del trigger del agente memoria
# ────────────────────────────────────────────────────────────────────
UMBRAL_TURNOS = 3      # cada N turnos del operador
UMBRAL_CHARS = 5000    # o si la vista del operador supera M chars


# ────────────────────────────────────────────────────────────────────
# Datos simulados (dominio de alertas, como ejemplos anteriores)
# ────────────────────────────────────────────────────────────────────
ALERTAS_ACTIVAS = [
    {"id": "A1", "tipo": "disco",   "nivel": "media"},
    {"id": "A2", "tipo": "memoria", "nivel": "crítica"},
    {"id": "A3", "tipo": "red",     "nivel": "baja"},
]
DETALLES_ALERTAS = {
    "A1": (
        "Disco al 78% de capacidad en /var. Crecimiento sostenido en las "
        "últimas 12 horas. Probablemente logs sin rotar."
    ),
    "A2": (
        "Uso de memoria al 95% en el servidor de aplicaciones. Procesos "
        "potencialmente colgados o memory leak en pagos-api."
    ),
    "A3": (
        "Latencia de red de 250ms hacia el data center secundario. "
        "Nodo intermedio posiblemente sobrecargado."
    ),
}


# ────────────────────────────────────────────────────────────────────
# Tools del agente operador
# ────────────────────────────────────────────────────────────────────
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
        "en el turno actual. Sé detallado y completo en el mensaje."
    ),
    parameters={"mensaje": {"description": "Respuesta al usuario.", "type": "string"}},
)
def responder(mensaje: str) -> dict:
    return {"mensaje": mensaje}


# ────────────────────────────────────────────────────────────────────
# Tool del agente memoria
# ────────────────────────────────────────────────────────────────────
@tool(
    description=(
        "Entrega el texto del resumen condensado. Sé conciso (3-4 "
        "oraciones) y preserva hechos clave, alertas mencionadas y datos."
    ),
    parameters={"texto": {"description": "Resumen condensado.", "type": "string"}},
)
def entregar_resumen(texto: str) -> dict:
    return {"texto": texto}


PROVIDER = "openai"
MODEL = "gpt-4.1-mini"
API_KEY = os.environ.get("OPEN_AI_API_KEY")

if not API_KEY:
    print("ERROR: falta OPEN_AI_API_KEY en el entorno.")
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────
# Vista del operador — `[último summary] + [turnos posteriores]`
# ────────────────────────────────────────────────────────────────────
# La vista filtra dos veces:
#   1. Por `origin`: solo entries del loop_operador (las del loop_memoria
#      no las ve — son trabajo de fondo).
#   2. Por id > id_del_último_summary: lo anterior al último resumen
#      queda "absorbido" en él; el operador no lo ve más, ve solo el
#      resumen + lo posterior.
def _render_entry_compacta(e, ahora: float) -> str:
    c = e.content if isinstance(e.content, dict) else {}
    edad = max(0, ahora - e.timestamp)
    if e.type == "prompt":
        return f"  [hace ~{edad:.0f}s] Usuario: {c.get('text', '')}"
    if e.type == "response":
        text = (c.get("text") or "").strip()
        return f"  [hace ~{edad:.0f}s] Asistente: {text}" if text else ""
    if e.type == "tool_call":
        name = c.get("name")
        args = c.get("arguments") or {}
        result = c.get("result")
        rs = json.dumps(result, ensure_ascii=False, default=str)
        if len(rs) > 200:
            rs = rs[:200] + "..."
        return f"  [hace ~{edad:.0f}s] {name}({args}) → {rs}"
    return ""


def vista_operador(history) -> str:
    rid_actual = current_run_id(history)
    ahora = time.time()

    # Solo entries del loop_operador (filtra el trabajo del agente memoria).
    entries_mias = [
        e for e in history.all()
        if isinstance(e.content, dict) and e.content.get("origin") == "loop_operador"
    ]

    # Último summary (es del operador, lo appendeamos manualmente con
    # origin=loop_operador para que la vista lo vea).
    summaries = [e for e in entries_mias if e.type == "summary"]
    ultimo_summary = summaries[-1] if summaries else None
    cutoff_id = ultimo_summary.id if ultimo_summary else 0

    # Narrativas (prompt/response/tool_call) posteriores al summary.
    narrativas = sorted(
        [e for e in entries_mias
         if e.id > cutoff_id
         and e.type in ("prompt", "response", "tool_call")],
        key=lambda e: e.id,
    )

    # Separar: lo del run actual va al final ("mi turno actual"); el
    # resto, "conversación posterior al resumen".
    mensaje_actual = ""
    actividad_actual, previo_posterior = [], []
    for e in narrativas:
        c = e.content
        if c.get("run_id") == rid_actual:
            if e.type == "prompt":
                mensaje_actual = c.get("text", "")
            else:
                actividad_actual.append(e)
        else:
            previo_posterior.append(e)

    lines: list[str] = []
    if ultimo_summary:
        lines.append("[Resumen de turnos anteriores]")
        lines.append(ultimo_summary.content.get("text", ""))
        cobertura = ultimo_summary.content.get("turnos_absorbidos")
        if cobertura:
            lines.append(f"(absorbe {cobertura} turnos previos)")
        lines.append("")

    if previo_posterior:
        lines.append("Conversación posterior al resumen:")
        for e in previo_posterior:
            r = _render_entry_compacta(e, ahora)
            if r:
                lines.append(r)
        lines.append("")

    lines.append(f"Mensaje actual del usuario: {mensaje_actual}")

    if actividad_actual:
        lines.append("")
        lines.append("Tu trabajo en este turno hasta ahora:")
        for e in actividad_actual:
            r = _render_entry_compacta(e, ahora)
            if r:
                lines.append(r)

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────
# Setup completo: agente memoria (sin loop), loop del operador, monitor
# ────────────────────────────────────────────────────────────────────
def construir_setup(history: History):
    history.add_view("vista_operador", vista_operador)

    # ── Agente memoria — un `InstantNeo` directo, sin envolver en Loop ─
    # Lo invocamos vía `agente_memoria.run(prompt)` desde la acción
    # del Monitor. Como no está envuelto en un Loop, no toca el
    # History compartido: toda su actividad queda en `last_run`.
    agente_memoria = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup=(
            "Eres un agente que resume conversaciones. Recibirás N turnos "
            "de un diálogo entre usuario y asistente. Genera un resumen "
            "conciso (3-4 oraciones) que preserve los temas tratados, "
            "los hechos clave y los datos importantes. Después llama "
            "`entregar_resumen(texto)` con el resumen."
        ),
        tools=[entregar_resumen],
        max_tokens=400,
    )

    # ── Acción `comprimir_memoria` (closure sobre agente_memoria) ───
    def comprimir_memoria(h: History) -> None:
        """Toma los turnos del operador posteriores al último summary,
        construye un prompt para el agente memoria, lo invoca como
        agente directo (sin loop), extrae el texto del resumen desde
        `last_run`, y appendea una entry `summary` al History."""

        # 1. Cutoff por último summary (de origin=loop_operador).
        summaries = [
            e for e in h.all()
            if e.type == "summary"
            and isinstance(e.content, dict)
            and e.content.get("origin") == "loop_operador"
        ]
        cutoff_id = summaries[-1].id if summaries else 0

        # 2. Entries narrativas del operador posteriores al cutoff.
        #    Incluimos `tool_call` porque ahí viven los datos reales
        #    (results de las consultas). Si solo pasáramos prompts y
        #    responses, el agente memoria perdería los datos cuando el
        #    operador no los repite en su texto de cierre.
        relevantes = sorted([
            e for e in h.all()
            if e.id > cutoff_id
            and isinstance(e.content, dict)
            and e.content.get("origin") == "loop_operador"
            and e.type in ("prompt", "response", "tool_call")
        ], key=lambda e: e.id)
        if not relevantes:
            return  # nada que resumir

        # 3. Construir bloque textual de la conversación. La tool de
        #    cierre (`responder`) la skippamos: su result es solo eco
        #    del mensaje, ya cubierto por el response/text.
        bloque = []
        n_prompts = 0
        for e in relevantes:
            c = e.content
            if e.type == "prompt":
                bloque.append(f"Usuario: {c.get('text', '')}")
                n_prompts += 1
            elif e.type == "response":
                t = (c.get("text") or "").strip()
                if t:
                    bloque.append(f"Asistente: {t}")
            elif e.type == "tool_call":
                name = c.get("name")
                if name == "responder":
                    # Las tool calls de cierre suelen contener el mismo
                    # texto que el `responder` muestra al usuario; lo
                    # incluimos como mensaje del asistente.
                    args = c.get("arguments") or {}
                    msg = (args.get("mensaje") or "").strip()
                    if msg:
                        bloque.append(f"Asistente: {msg}")
                else:
                    args = c.get("arguments") or {}
                    result = c.get("result")
                    rs = json.dumps(result, ensure_ascii=False, default=str)
                    if len(rs) > 400:
                        rs = rs[:400] + "..."
                    bloque.append(
                        f"Asistente consultó {name}({args}) → {rs}"
                    )
        prompt_memoria = (
            "Resume los siguientes turnos de una conversación entre un "
            "usuario y un asistente de operaciones. Conserva los temas "
            "tratados, las alertas mencionadas (con ID y nivel) y los "
            "datos concretos de cada consulta. Máximo 4 oraciones."
            f"\n\n{chr(10).join(bloque)}"
        )

        # 4. Invocar al agente memoria como agente directo (sin Loop).
        #    NO toca el History compartido; todo queda en `last_run`.
        agente_memoria.run(prompt_memoria)

        # 5. Extraer texto del tool_execution de `entregar_resumen`.
        last_run = agente_memoria.last_run
        if last_run is None or not last_run.tool_executions:
            return
        te = next(
            (x for x in reversed(last_run.tool_executions)
             if x.name == "entregar_resumen"),
            None,
        )
        if te is None:
            return  # el agente memoria no llamó la tool de cierre
        texto = (te.arguments or {}).get("texto", "")
        if not texto:
            return

        # 6. Appendear summary al History con origin=loop_operador para
        #    que la vista del operador lo vea como propio.
        h.append(
            author="memoria",
            type="summary",
            content={
                "origin": "loop_operador",
                "text": texto,
                "turnos_absorbidos": n_prompts,
                "rango_ids": (relevantes[0].id, relevantes[-1].id),
            },
        )

    # ── Condición del trigger ───────────────────────────────────────
    def condicion_resumir(h: History) -> bool:
        # Solo evaluamos al cierre de un turno del operador. El cierre es
        # cuando la última tool_call de este step es `responder` de
        # origin=loop_operador.
        ultima_tc = next(
            (e for e in reversed(h.all()) if e.type == "tool_call"),
            None,
        )
        if ultima_tc is None:
            return False
        c = ultima_tc.content if isinstance(ultima_tc.content, dict) else {}
        if c.get("name") != "responder" or c.get("origin") != "loop_operador":
            return False

        # Criterio A: N turnos del operador desde el último summary.
        summaries = [
            e for e in h.all()
            if e.type == "summary"
            and isinstance(e.content, dict)
            and e.content.get("origin") == "loop_operador"
        ]
        cutoff_id = summaries[-1].id if summaries else 0
        runs_post = [
            e for e in h.all()
            if e.type == "run_start"
            and isinstance(e.content, dict)
            and e.content.get("origin") == "loop_operador"
            and e.id > cutoff_id
        ]
        if len(runs_post) >= UMBRAL_TURNOS:
            return True

        # Criterio B: tamaño del prompt rendereado.
        try:
            texto = h.export("vista_operador")
            if isinstance(texto, str) and len(texto) > UMBRAL_CHARS:
                return True
        except KeyError:
            pass
        return False

    # ── Monitor del operador con la regla de compresión ────────────
    # Como `comprimir_memoria` invoca al agente memoria SIN tocar el
    # History compartido, no hay riesgo de "ensuciar" la última
    # tool_call. El sugar `stop_tool="responder"` (definido en el
    # constructor del Loop más abajo) sigue funcionando limpiamente.
    monitor_op = Monitor(name="monitor_operador")
    monitor_op.add_rule(condicion_resumir, comprimir_memoria)

    # ── Agente operador + su loop ──────────────────────────────────
    agente_operador = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup=(
            "Eres un asistente conversacional de operaciones. En cada "
            "turno trabajas internamente con las tools que necesites y al "
            "final llamas `responder(mensaje)` con una respuesta detallada "
            "para el usuario.\n\n"
            "Si en la conversación previa ya consultaste algo, no lo "
            "vuelvas a consultar — reutiliza la información. Si hay un "
            "[Resumen de turnos anteriores] al inicio del contexto, "
            "trátalo como verdad sobre lo que ya pasó."
        ),
        tools=[obtener_alertas, obtener_detalle_alerta, responder],
        max_tokens=1500,
    )
    agente_operador.name = "agente_operador"
    loop_operador = InstantLoop(
        agent=agente_operador,
        history=history,
        name="loop_operador",
        view="vista_operador",
        monitors=monitor_op,
        stop_tool="responder",
        max_steps=4,
    )

    return loop_operador


# ────────────────────────────────────────────────────────────────────
# Conversación del demo
# ────────────────────────────────────────────────────────────────────
CONVERSACION = [
    "Lista las alertas activas del sistema.",
    "Cuéntame el detalle de A1.",
    "Cuéntame el detalle de A2.",
    "Cuéntame el detalle de A3.",
    "Compara las tres alertas y dime cuál priorizar.",
    "Emite un reporte final con la acción concreta para la priorizada.",
]


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    history = History(name="chat_con_memoria")
    loop_op = construir_setup(history)

    section(f"CHAT — {len(CONVERSACION)} turnos del usuario")
    print(f"  trigger del agente memoria:")
    print(f"    cada {UMBRAL_TURNOS} turnos del operador, o")
    print(f"    si la vista supera {UMBRAL_CHARS} chars")

    tam_vista_por_turno = []
    for i, prompt in enumerate(CONVERSACION, start=1):
        antes_n_summaries = len(history.by_type("summary"))
        r = loop_op.run(prompt)
        despues_n_summaries = len(history.by_type("summary"))
        tam = len(history.export("vista_operador"))
        tam_vista_por_turno.append(tam)
        disparado = "📚 RESUMEN" if despues_n_summaries > antes_n_summaries else ""
        print(
            f"  turno {i}: {r.terminated_reason:<12} "
            f"{r.total_steps} steps  | vista: {tam:>5} chars  {disparado}"
        )

    # ────────────────────────────────────────────────────────────────
    # Resultados
    # ────────────────────────────────────────────────────────────────
    summaries = history.by_type("summary")
    section(f"RESÚMENES GENERADOS — {len(summaries)}")
    for i, s in enumerate(summaries, start=1):
        c = s.content
        print(f"  Resumen #{i} — absorbe {c.get('turnos_absorbidos')} turnos "
              f"(ids {c.get('rango_ids')}):")
        print(f"    {c.get('text', '')}")
        print()

    section("EVOLUCIÓN DEL TAMAÑO DE LA VISTA DEL OPERADOR")
    for i, tam in enumerate(tam_vista_por_turno, start=1):
        bar = "█" * (tam // 200)
        print(f"  turno {i}: {tam:>5} chars  {bar}")

    section("ÚLTIMO RENDER DE vista_operador (lo que vería el próximo turno)")
    print(history.export("vista_operador"))

    section("RESUMEN ESTADÍSTICO")
    print(f"  turnos del usuario       : {len(CONVERSACION)}")
    print(f"  resúmenes generados      : {len(summaries)}")
    print(f"  invocaciones agente mem. : {len(summaries)}")
    print(f"  entries en History       : {len(history.all())}")
    print(f"  tamaño vista turno 1     : {tam_vista_por_turno[0]} chars")
    print(f"  tamaño vista último turno: {tam_vista_por_turno[-1]} chars")

    # ────────────────────────────────────────────────────────────────
    # Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    assert len(summaries) >= 1, "se esperaba al menos un resumen generado"
    assert tam_vista_por_turno[-1] < max(tam_vista_por_turno) + 1, (
        "se esperaba que el resumen estabilizara el tamaño de la vista"
    )

    print("\n✅ Ejemplo 08 completado correctamente.")


if __name__ == "__main__":
    main()
