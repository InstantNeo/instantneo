"""
Ejemplo 02 — Anatomía del History y de las Entries
====================================================

Caso funcional
--------------
En el ejemplo 01 el `History` era una caja negra que el Loop manejaba
internamente. En este ejemplo lo **creas tú**, se lo pasas al Loop, y
después del run lo abres por dentro: ¿qué hay guardado? ¿qué campos tiene
cada entrada? ¿cómo consultas el log? ¿cómo lo serializas para guardarlo
en disco o auditar después?

Eso es lo que vamos a recorrer acá. La tarea del agente es la misma del
01 (revisar alertas y reportar) porque el foco no está en el agente,
está en **el dato**.

Anatomía rápida
---------------
Un `History` es un log inmutable, append-only, de `Entry`s. Cada `Entry`
es un dataclass congelado con 6 campos:

    id         : int    — auto-incremental desde 1
    author     : str    — quién emitió la entry ("user", "orchestrator",
                          el nombre del agente, etc.)
    timestamp  : float  — UTC, asignado en append
    type       : str    — string libre con convención
                          ("prompt", "response", "tool_call",
                           "run_start", "step_start", ...)
    content    : dict   — payload, shape específico al tipo
    refs       : tuple  — ids de otras entries con las que se relaciona

El `History` no valida `type` ni el shape de `content`. Es honesto: tú
defines la convención que necesitas. Los tipos que verás más abajo
(`prompt`, `tool_call`, `run_start`, etc.) son la convención que usa el
`InstantLoop`; otros orquestadores pueden usar otras.

Cómo correr
-----------
    python3 examples/02_history_anatomy.py
"""
import json
import os
import sys
from dataclasses import asdict
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
# Tools (las mismas del ejemplo 01)
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
# Helper de impresión: imprime una entry con sus 6 campos visibles
# ────────────────────────────────────────────────────────────────────
def print_entry(entry, label: str = "", content_cap: int = 800) -> None:
    """Imprime una Entry mostrando sus 6 campos. Trunca content si excede
    `content_cap` caracteres para evitar volcados gigantes (útil para
    `run_start`, que incluye el config completo del agente)."""
    if label:
        print(f"  [{label}]")
    print(f"  id        = {entry.id}")
    print(f"  author    = {entry.author!r}")
    print(f"  timestamp = {entry.timestamp:.3f}")
    print(f"  type      = {entry.type!r}")
    print(f"  refs      = {entry.refs}")
    content_str = json.dumps(entry.content, indent=2, ensure_ascii=False, default=str)
    if len(content_str) > content_cap:
        content_str = content_str[:content_cap] + f"\n  ... [truncado, total {len(content_str)} chars]"
    # Indentamos cada línea del content para alinear visualmente.
    indented = "\n".join("  " + line for line in content_str.splitlines())
    print(f"  content   =\n{indented}")


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    # ────────────────────────────────────────────────────────────────
    # 1. Creas el History fuera del Loop
    # ────────────────────────────────────────────────────────────────
    # Acá viene el cambio respecto del 01: instancias el History tú, en
    # tu código, y se lo pasas al Loop por argumento. Después del run, el
    # History sigue siendo tuyo — el Loop no lo "consume", solo lo
    # alimenta.
    history = History(name="anatomia_demo")
    assert history.all() == [], "el history recién creado está vacío"

    # ────────────────────────────────────────────────────────────────
    # 2. Construyes agente y loop, pasándole el history
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
        history=history,            # ← acá lo pasas
        name="ejemplo_02",
        stop_tool="reportar",
        max_steps=8,
    )

    # ────────────────────────────────────────────────────────────────
    # 3. Corres
    # ────────────────────────────────────────────────────────────────
    print(">>> Ejecutando el loop...")
    result = loop.run("Revisa las alertas y emite un reporte.")
    print(f">>> Terminó: {result.terminated_reason} en {result.total_steps} steps\n")

    # El history que el Loop alimentó es exactamente el que tú creaste:
    assert result.history is history, "el Loop no clonó el history; lo alimentó"

    # ────────────────────────────────────────────────────────────────
    # 4. Anatomía de una Entry — el shape crudo
    # ────────────────────────────────────────────────────────────────
    # Imprimimos la primera entry del log, que es el run_start emitido
    # por el orchestrator (el Loop). Muestra los 6 campos del dataclass.
    section("ANATOMÍA DE UNA ENTRY — la primera del log")
    primera = history.all()[0]
    print_entry(primera, label=f"primera entry (de {len(history.all())} totales)")

    # ────────────────────────────────────────────────────────────────
    # 5. El `content` varía según `type` — tres ejemplos representativos
    # ────────────────────────────────────────────────────────────────
    # `content` es un dict libre cuyo shape depende del `type`. Mostramos
    # tres tipos comunes para que veas la diferencia.

    section("CONTENT POR TIPO — entry 'prompt' (qué pidió el usuario)")
    prompt_entry = history.by_type("prompt")[0]
    print_entry(prompt_entry)

    section("CONTENT POR TIPO — entry 'tool_call' (qué tool llamó el agente)")
    tool_call_entry = history.by_type("tool_call")[0]
    print_entry(tool_call_entry)

    # El run_start incluye el config completo del agente (provider, modelo,
    # role_setup resuelto, schemas de las tools, etc.). Es la "cabecera"
    # autocontenida del run — útil para auditoría y replay. Lo truncamos
    # al imprimir porque puede ser largo.
    section("CONTENT POR TIPO — entry 'run_start' (cabecera del run)")
    run_start_entry = history.by_type("run_start")[0]
    print_entry(run_start_entry, content_cap=500)

    # ────────────────────────────────────────────────────────────────
    # 6. APIs de inspección del History
    # ────────────────────────────────────────────────────────────────
    # Cuatro queries que cubren la mayoría de los casos:
    #   all()              → lista completa en orden cronológico
    #   by_type(t)         → filtra por type
    #   by_author(a)       → filtra por author
    #   get(id)            → entry por id (KeyError si no existe)
    section("APIs DE INSPECCIÓN")
    print(f"  history.all()                     → {len(history.all())} entries")
    print(f"  history.by_type('tool_call')      → {len(history.by_type('tool_call'))} entries")
    print(f"  history.by_type('response')       → {len(history.by_type('response'))} entries")
    print(f"  history.by_author('orchestrator') → {len(history.by_author('orchestrator'))} entries")
    print(f"  history.by_author('user')         → {len(history.by_author('user'))} entries")
    print(f"  history.get(1).type               → {history.get(1).type!r}")

    # Ejemplo de uso combinado: extraer todos los nombres de tools llamadas.
    nombres_tools = [tc.content.get("name") for tc in history.by_type("tool_call")]
    print(f"  tools llamadas en orden           → {nombres_tools}")

    # ────────────────────────────────────────────────────────────────
    # 7. Serialización — guardar y reconstruir el log
    # ────────────────────────────────────────────────────────────────
    # `to_dicts()` devuelve una lista de dicts JSON-safe (refs como
    # listas, no tuples). `to_json()` es lo mismo serializado a string.
    # `History.from_dicts(...)` reconstruye una History con los mismos
    # ids, timestamps y refs (los `_views` registradas NO se serializan
    # — esa es decisión consciente).
    section("SERIALIZACIÓN — roundtrip a dicts")
    dicts = history.to_dicts()
    print(f"  history.to_dicts() → list de {len(dicts)} dicts")
    print(f"  primera entry como dict:")
    print("  " + json.dumps(dicts[0], indent=2, ensure_ascii=False, default=str)[:400] + " ...")

    rebuilt = History.from_dicts(dicts)
    assert len(rebuilt.all()) == len(history.all())
    assert rebuilt.get(1).type == history.get(1).type
    print(f"\n  History.from_dicts(dicts) → reconstruida con {len(rebuilt.all())} entries OK")

    # ────────────────────────────────────────────────────────────────
    # 8. Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    assert history.all()[0].type == "run_start"
    assert any(tc.content.get("name") == "reportar" for tc in history.by_type("tool_call"))
    assert all(isinstance(e.refs, tuple) for e in history.all()), "refs es siempre tuple en memoria"

    print("\n✅ Ejemplo 02 completado correctamente.")


if __name__ == "__main__":
    main()
