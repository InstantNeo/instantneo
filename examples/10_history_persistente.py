"""
Ejemplo 10 — History persistente: chat que sobrevive entre sesiones
=====================================================================

Caso funcional
--------------
El proceso muere y el History se pierde. Eso no sirve para chats reales:
queremos que un usuario hable hoy, cierre el programa, vuelva mañana, y
el agente lo recuerde donde lo dejó.

Solución: serializar el History a disco después de cada sesión y
cargarlo al inicio de la próxima. El History tiene dos métodos
complementarios:

  - ``history.to_dicts()``     → lista de dicts JSON-safe.
  - ``History.from_dicts(...)`` → reconstruye un History idéntico
    (mismos ids, timestamps, refs, type, content).

Una llamada a `json.dumps`/`json.loads` los conecta con el disco.

Qué muestra este ejemplo
------------------------
Un solo script simula dos sesiones de chat con el **mismo usuario** y
**el mismo agente**, separadas por un "reinicio del proceso":

1. **Sesión 1**: arrancamos con History vacío. El usuario se presenta
   ("Soy María del Carmen, ingeniera de pagos") y consulta algo.
   Después guardamos el History en disco.
2. **Reinicio**: borramos las referencias a `history` y `loop` (como
   si el proceso hubiera muerto).
3. **Sesión 2**: cargamos el History desde disco con `from_dicts`.
   Construimos un Loop nuevo sobre ese History. El usuario pregunta:
   "¿Te acuerdas quién soy?" — el agente debe responder con el nombre
   y rol del usuario, porque están en el History recargado.

Las vistas no se serializan (son funciones, no datos). Por eso al
reconstruir el History hay que **registrar las vistas otra vez** antes
de construir el Loop. El comentario en `construir_loop` lo enfatiza.

Cómo correr
-----------
    python3 examples/10_history_persistente.py
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
from instantneo.loop.default_view import loop_default


# ────────────────────────────────────────────────────────────────────
# Tools
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
# Vista que muestra TODO el historial (todos los runs)
# ────────────────────────────────────────────────────────────────────
# Para multi-sesión necesitamos que el agente vea los runs anteriores
# (la sesión 1 dejó runs cuyo id ya no es el actual). Reusamos
# `loop_default` pero le pedimos `show_all_runs=True` mediante un
# closure trivial. Es función pura: misma History → mismo output.
#
# Por qué `show_all_runs=True` es necesario en multi-sesión: la vista
# por defecto de `loop_default` filtra por `current_run_id`, que es el
# id del último `run_start` del History. Después de cargar desde
# disco, ese id apunta al último run de la sesión 1; cuando arranca el
# nuevo `loop.run()` de la sesión 2, se appendea otro `run_start` y
# el `current_run_id` salta al nuevo — dejando todo lo de la sesión 1
# fuera de la vista. Con `show_all_runs=True` ignoramos ese filtro y
# el agente ve la conversación entera.
def vista_todos_los_runs(history) -> object:
    return loop_default(history, show_all_runs=True)


def construir_loop(history: History) -> InstantLoop:
    """Construye el agente y el Loop. Funciona tanto si el History es
    nuevo como si fue reconstruido con `from_dicts`.

    Importante: las vistas NO se serializan junto con el History
    (son funciones, no datos). Hay que registrarlas otra vez en
    cada sesión, antes de construir el Loop.
    """
    history.add_view("todos_los_runs", vista_todos_los_runs)

    agente = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup=(
            "Eres un asistente conversacional de operaciones. Recuerda "
            "lo que el usuario te contó en sesiones anteriores y úsalo "
            "para personalizar tus respuestas. Al final de cada turno "
            "llamas `responder(mensaje)`."
        ),
        tools=[obtener_alertas, responder],
    )
    agente.name = "agente_operador"
    return InstantLoop(
        agent=agente,
        history=history,
        name="loop_operador",
        view="todos_los_runs",
        stop_tool="responder",
        max_steps=4,
    )


def extraer_ultima_respuesta(history: History, run_id: str) -> str:
    """Devuelve el `mensaje` del último `responder` del run dado."""
    tc = next(
        (e for e in reversed(history.by_type("tool_call"))
         if e.content.get("name") == "responder"
         and e.content.get("run_id") == run_id),
        None,
    )
    if not tc:
        return ""
    return (tc.content.get("arguments") or {}).get("mensaje", "")


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


# ────────────────────────────────────────────────────────────────────
# Path del checkpoint en disco
# ────────────────────────────────────────────────────────────────────
CHECKPOINT_PATH = Path("/tmp/instantneo_ejemplo10_history.json")


def main() -> None:
    # Limpieza para que el ejemplo sea reproducible cuando se vuelve
    # a correr.
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()

    # ════════════════════════════════════════════════════════════════
    # SESIÓN 1 — primera vez que el usuario abre el chat
    # ════════════════════════════════════════════════════════════════
    section("SESIÓN 1 — primera vez del usuario")
    history1 = History(name="chat_persistente")
    loop1 = construir_loop(history1)

    r1 = loop1.run(
        "Hola, soy María del Carmen, ingeniera senior del equipo de "
        "pagos. Quiero hacer una consulta inicial: ¿hay alertas activas "
        "en el sistema?"
    )
    print(f"  resultado: {r1.terminated_reason} ({r1.total_steps} steps)")

    respuesta1 = extraer_ultima_respuesta(history1, r1.run_id)
    print(f"\n  Respuesta del agente:")
    print(f"    {respuesta1}")
    print(f"\n  History tiene {len(history1.all())} entries.")

    # ────────────────────────────────────────────────────────────────
    # Persistir el History a disco
    # ────────────────────────────────────────────────────────────────
    # `to_dicts()` devuelve una lista de dicts JSON-safe (refs vienen
    # como listas, no tuples — JSON no tiene tuple). `json.dumps` los
    # serializa. Esto es lo único que hay que guardar.
    #
    # Lo que NO se serializa: las vistas. Son funciones Python
    # registradas con `add_view`, no datos. Por eso `construir_loop`
    # las registra otra vez en cada sesión, sobre el History
    # recargado.
    section("PERSISTIENDO EL HISTORY")
    dicts = history1.to_dicts()
    CHECKPOINT_PATH.write_text(
        json.dumps(dicts, indent=2, ensure_ascii=False, default=str)
    )
    tamaño_kb = CHECKPOINT_PATH.stat().st_size / 1024
    print(f"  guardado en: {CHECKPOINT_PATH}")
    print(f"  tamaño     : {tamaño_kb:.1f} KB ({len(dicts)} entries)")

    # ────────────────────────────────────────────────────────────────
    # "Reinicio del proceso" — simulamos perder todo lo que vive en RAM
    # ────────────────────────────────────────────────────────────────
    # En un caso real, acá termina el script. En este ejemplo, borramos
    # explícitamente las referencias para mostrar que la sesión 2 NO
    # depende de nada en memoria — solo del archivo.
    del history1, loop1

    # ════════════════════════════════════════════════════════════════
    # SESIÓN 2 — otro día, mismo usuario, "nuevo proceso"
    # ════════════════════════════════════════════════════════════════
    section("SESIÓN 2 — recarga desde disco")
    raw = CHECKPOINT_PATH.read_text()
    dicts_cargados = json.loads(raw)
    history2 = History.from_dicts(dicts_cargados)
    print(f"  History reconstruida con {len(history2.all())} entries.")
    print(f"  primera entry: id={history2.all()[0].id} "
          f"type={history2.all()[0].type!r}")
    print(f"  última entry : id={history2.all()[-1].id} "
          f"type={history2.all()[-1].type!r}")

    # Construir loop nuevo sobre el History recargado.
    loop2 = construir_loop(history2)

    # Pregunta del usuario que solo se puede responder bien si el agente
    # tiene el contexto de la sesión 1.
    r2 = loop2.run(
        "Hola de nuevo. ¿Te acuerdas quién soy y cuál es mi rol? "
        "¿Y qué te consulté la última vez?"
    )
    print(f"\n  resultado turno 2: {r2.terminated_reason} ({r2.total_steps} steps)")

    respuesta2 = extraer_ultima_respuesta(history2, r2.run_id)
    print(f"\n  Respuesta del agente:")
    print(f"    {respuesta2}")

    # ────────────────────────────────────────────────────────────────
    # Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    # 1. El History reconstruido preserva ids y timestamps originales:
    #    `from_dicts` no los reasigna. Esto es importante porque las
    #    refs entre entries (cuando existen) siguen apuntando bien, y
    #    una nueva `to_dicts()` daría exactamente el mismo output que
    #    el que cargamos del disco.
    primera_entry = history2.all()[0]
    assert primera_entry.id == 1, "from_dicts debe preservar ids"
    assert isinstance(primera_entry.refs, tuple), \
        "refs se restaura como tuple, no list"

    # 2. El agente debe reconocer datos de la sesión 1 en su respuesta.
    respuesta_lower = respuesta2.lower()
    palabras_clave = ("maría", "carmen", "ingeniera", "pagos", "alertas")
    matches = [k for k in palabras_clave if k in respuesta_lower]
    assert len(matches) >= 2, (
        f"el agente debería mencionar al menos 2 datos de la sesión 1; "
        f"encontró: {matches}; respuesta: {respuesta2[:200]!r}"
    )
    print(f"\n  ✓ el agente mencionó datos de la sesión 1: {matches}")

    print("\n✅ Ejemplo 10 completado correctamente.")


if __name__ == "__main__":
    main()
