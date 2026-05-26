"""
Ejemplo 20 — Delegación a sub-agentes envueltos como tools (problema abierto)
==============================================================================

Caso funcional
--------------
Un analista del comercio recibe un problema vago: "se cancelaron
varios pedidos esta semana, analizá las razones y dame un panorama
corto". Los datos llegan como una lista de registros con texto libre
en el campo `razon`.

Hay tres **tareas funcionales** ya implementadas en otros lugares de
la organización, cada una resuelta por un sub-agente especializado:

- **`resumir_texto`** — `InstantNeo` simple (sin Loop). Comprime un
  texto largo a N líneas. Es una tarea de un solo turno.
- **`explorar_dataset_iterativo`** — `InstantNeo` envuelto en
  `InstantLoop`. Navega registros, agrupa, filtra. Necesita varios
  turnos para iterar.
- **`extraer_entidades_clave`** — `InstantNeo` simple. Extrae entidades
  nombradas (productos, montos, motivos) de un texto.

Esas tareas se exponen al supervisor como tres tools, agrupadas en un
capability `tareas_especializadas` con `global_instructions` que
explica cuándo conviene cada una.

El supervisor recibe el problema **abierto** y resuelve solo cuántos
pasos dar y qué delegar. No le imponemos un guion.

Qué muestra este ejemplo
------------------------
1. Cómo envolver `agent.run()` y `loop.run()` adentro de funciones
   decoradas con `@tool` — el patrón "sub-agente como tool".
2. Mezclar sub-agentes con Loop interno y sin Loop interno, dentro del
   mismo capability.
3. Usar `global_instructions` del capability como prompt de **routing**:
   describe cuándo se elige cada delegación.
4. Que un supervisor con problema abierto puede resolver con la
   cantidad de pasos que necesite — observable en el History.

Cómo correr
-----------
    python3 examples/20_delegacion_tareas_funcionales.py
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

from instantneo import AgentCapabilities, History, InstantLoop, InstantNeo, tool


# ────────────────────────────────────────────────────────────────────
# Dataset sintético — 8 pedidos cancelados con razón en texto libre
# ────────────────────────────────────────────────────────────────────
# Algunas razones son recurrentes (demoras, productos rotos, precios
# competencia); otras son únicas. La idea es que el supervisor
# necesite agrupar/clasificar para encontrar patrones — un trabajo no
# trivial para un solo turno.
PEDIDOS_CANCELADOS = [
    {"id": "P-301", "monto": 850, "razon": "Cliente vio el mismo termo $150 más barato en otra tienda y pidió cancelación."},
    {"id": "P-302", "monto": 320, "razon": "Pedido se demoró más de 7 días en salir del depósito; el cliente reclamó y canceló."},
    {"id": "P-303", "monto": 145, "razon": "Yerba llegó con el paquete rasgado, no se animó a consumirla, devolvió."},
    {"id": "P-304", "monto": 480, "razon": "Cliente cambió de opinión, ya no le interesaba el modelo de termo."},
    {"id": "P-305", "monto": 215, "razon": "Demora en la entrega de más de 10 días; el cliente compró el equivalente en supermercado."},
    {"id": "P-306", "monto": 920, "razon": "Encontró un combo más barato en marketplace; canceló este y compró allá."},
    {"id": "P-307", "monto": 380, "razon": "Bombilla doblada al recibirla; canceló sin esperar reposición."},
    {"id": "P-308", "monto": 670, "razon": "Demora del envío sumada a falta de respuesta del soporte; canceló enojado."},
]


PROVIDER = "openai"
MODEL = "gpt-4.1-mini"
API_KEY = os.environ.get("OPEN_AI_API_KEY")

if not API_KEY:
    print("ERROR: falta OPEN_AI_API_KEY en el entorno.")
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────
# SUB-AGENTE 1 — Resumir texto. InstantNeo simple, sin Loop.
# ────────────────────────────────────────────────────────────────────
# Caso típico de single-shot: no necesita razonar en pasos. Devuelve
# texto comprimido a la cantidad de líneas pedida.
agente_resumidor = InstantNeo(
    provider=PROVIDER, model=MODEL, api_key=API_KEY,
    role_setup=(
        "Eres un compresor de texto. Recibís un texto y devolvés una "
        "versión condensada en 3 líneas o menos, conservando lo "
        "esencial. No agregues opiniones ni preámbulos."
    ),
    max_tokens=200,
)


# ────────────────────────────────────────────────────────────────────
# SUB-AGENTE 2 — Explorar dataset iterativamente. InstantNeo con Loop.
# ────────────────────────────────────────────────────────────────────
# Esta tarea sí se beneficia de loop: el agente puede llamar tools
# auxiliares para filtrar/agrupar paso a paso. Para mantener el
# ejemplo cerrado, le damos UNA tool auxiliar de agrupado y le
# pedimos que itere hasta tener una conclusión.
_DATASET_TEMPORAL: dict = {"valor": []}   # estado entre la tool y el sub-agente


@tool(
    description=(
        "Cuenta cuántos registros del dataset cargado mencionan una "
        "palabra clave en su campo `razon`. Útil para validar hipótesis."
    ),
    parameters={
        "palabra": {"type": "string", "description": "Palabra clave a buscar (case-insensitive)."},
    },
)
def contar_menciones_en_razon(palabra: str) -> dict:
    pal = palabra.lower()
    coincidencias = [r["id"] for r in _DATASET_TEMPORAL["valor"] if pal in r.get("razon", "").lower()]
    return {"palabra": palabra, "cantidad": len(coincidencias), "ids": coincidencias}


agente_explorador = InstantNeo(
    provider=PROVIDER, model=MODEL, api_key=API_KEY,
    role_setup=(
        "Eres explorador de datasets. Recibís un dataset de registros y "
        "una pregunta. Usá `contar_menciones_en_razon` para validar "
        "hipótesis sobre qué palabras clave aparecen y cuántas veces. "
        "Llegá a una conclusión breve y entregala. No expliques tu proceso."
    ),
    tools=[contar_menciones_en_razon],
    max_tokens=400,
)


# ────────────────────────────────────────────────────────────────────
# SUB-AGENTE 3 — Extraer entidades. InstantNeo simple, sin Loop.
# ────────────────────────────────────────────────────────────────────
agente_extractor = InstantNeo(
    provider=PROVIDER, model=MODEL, api_key=API_KEY,
    role_setup=(
        "Eres extractor de entidades. Recibís un texto y devolvés una "
        "lista corta de las entidades clave en formato:\n"
        "- producto: <nombre>\n"
        "- monto: <valor>\n"
        "- motivo: <tipo>\n"
        "Si una categoría no aparece en el texto, omitila. Sin texto "
        "adicional."
    ),
    max_tokens=250,
)


# ────────────────────────────────────────────────────────────────────
# Tools que envuelven a los sub-agentes
# ────────────────────────────────────────────────────────────────────
# Cada @tool recibe argumentos planos del supervisor, los pasa al
# sub-agente y le devuelve un dict simple. El supervisor ve estas
# tools como cualquier otra — no sabe ni le importa que adentro corre
# otro agente.

@tool(
    description="Resume un texto a 3 líneas o menos.",
    parameters={"texto": {"type": "string", "description": "Texto a resumir."}},
)
def resumir_texto(texto: str) -> dict:
    respuesta = agente_resumidor.run(texto)
    out = respuesta.get("text") if isinstance(respuesta, dict) else str(respuesta)
    return {"resumen": out}


@tool(
    description=(
        "Explora iterativamente un dataset de registros respondiendo a una "
        "pregunta de análisis. Tarea CARA (multi-step internamente), "
        "usala UNA sola vez por problema."
    ),
    parameters={
        "dataset_json": {"type": "string", "description": "Dataset serializado a JSON."},
        "pregunta":     {"type": "string", "description": "Pregunta de análisis (ej: ¿cuáles son los motivos más frecuentes?)."},
    },
)
def explorar_dataset_iterativo(dataset_json: str, pregunta: str) -> dict:
    # Cargamos el dataset al estado temporal para que la tool del
    # explorador (`contar_menciones_en_razon`) lo vea.
    _DATASET_TEMPORAL["valor"] = json.loads(dataset_json)

    loop = InstantLoop(
        agent=agente_explorador, history=History(),
        name="explorador", max_steps=6,
    )
    loop.run(
        f"Dataset cargado ({len(_DATASET_TEMPORAL['valor'])} registros). "
        f"Pregunta: {pregunta}"
    )
    responses = loop.history.by_type("response")
    conclusion = next(
        (r.content.get("text") for r in reversed(responses) if r.content.get("text")),
        "",
    )
    return {"conclusion": conclusion, "steps": loop.history.by_type("step_start").__len__()}


@tool(
    description="Extrae entidades clave (producto, monto, motivo) de un texto.",
    parameters={"texto": {"type": "string", "description": "Texto a analizar."}},
)
def extraer_entidades_clave(texto: str) -> dict:
    respuesta = agente_extractor.run(texto)
    out = respuesta.get("text") if isinstance(respuesta, dict) else str(respuesta)
    return {"entidades": out}


@tool(
    description=(
        "Cierra el análisis entregando el panorama final al sistema. "
        "Llamala UNA sola vez cuando tengas la conclusión consolidada."
    ),
    parameters={"panorama_md": {"type": "string", "description": "Panorama final en markdown."}},
)
def entregar_panorama_final(panorama_md: str) -> dict:
    return {"panorama": panorama_md}


# ────────────────────────────────────────────────────────────────────
# Capability `tareas_especializadas` — agrupa las 3 tools-delegado +
# prompt de routing
# ────────────────────────────────────────────────────────────────────
# Las `global_instructions` describen QUÉ hace cada tool y CUÁNDO
# conviene. Es el "manual de uso" que el supervisor lee al recibir el
# capability. El supervisor decide solo qué delegar.
tareas_especializadas = AgentCapabilities(
    name="tareas_especializadas",
    description="Tareas funcionales delegables a sub-agentes especializados.",
    skills=[resumir_texto, explorar_dataset_iterativo, extraer_entidades_clave,
            entregar_panorama_final],
    global_instructions=(
        "Tenés tres tareas funcionales y una de cierre.\n\n"
        "- `resumir_texto(texto)`: comprime un texto a 3 líneas.\n"
        "- `explorar_dataset_iterativo(dataset_json, pregunta)`: navega "
        "una lista de registros para responder una pregunta de análisis. "
        "Es CARA, usala una sola vez si la usás.\n"
        "- `extraer_entidades_clave(texto)`: extrae entidades nombradas "
        "(producto, monto, motivo) de un texto.\n"
        "- `entregar_panorama_final(panorama_md)`: cerrá el trabajo "
        "entregando el panorama. Tiene que ser tu última acción. "
        "No pidas confirmaciones ni esperes respuestas."
    ),
)


# ────────────────────────────────────────────────────────────────────
# Supervisor — recibe el problema abierto
# ────────────────────────────────────────────────────────────────────
# El `role_setup` describe quién es y le dice que use el capability
# disponible. NO le damos pasos prefijados. Le pasamos el dataset
# entero y la pregunta abierta.
supervisor = InstantNeo(
    provider=PROVIDER, model=MODEL, api_key=API_KEY,
    role_setup=(
        "Eres analista del comercio. Te llega un problema operativo y "
        "tenés tareas funcionales para delegar. Resolvé con la cantidad "
        "de pasos que necesites — ni más ni menos."
    ),
    tools=tareas_especializadas,
    max_tokens=500,
)


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    section("CAPABILITY DE ROUTING")
    print(f"  name        : {tareas_especializadas.name}")
    print(f"  tools       : {tareas_especializadas.get_tool_names()}")
    print(f"  routing prompt (preview):")
    for ln in tareas_especializadas.get_global_instructions().splitlines()[:5]:
        print(f"    {ln}")

    section("SYSTEM PROMPT DEL SUPERVISOR (resumido)")
    resolved = supervisor.get_resolved_role_setup()
    print(f"  longitud: {len(resolved)} chars")

    # ────────────────────────────────────────────────────────────────
    # Corrida — el supervisor recibe el problema y delega libremente
    # ────────────────────────────────────────────────────────────────
    # `stop_tool` hace que el loop termine cuando el supervisor llame
    # esa tool específica. Ergonomía limpia: el agente "entrega" su
    # trabajo en lugar de pedir confirmación al usuario.
    loop = InstantLoop(
        agent=supervisor, history=History(),
        name="supervisor", max_steps=10,
        stop_tool="entregar_panorama_final",
    )
    section("PROBLEMA AL SUPERVISOR")
    print("  'Se cancelaron 8 pedidos esta semana. Analizá los motivos y")
    print("   dame un panorama corto de qué está pasando.'")
    print(f"  (le pasamos el dataset de {len(PEDIDOS_CANCELADOS)} registros)")

    result = loop.run(
        "Se cancelaron varios pedidos esta semana. Acá está el dataset "
        f"completo:\n\n{json.dumps(PEDIDOS_CANCELADOS, ensure_ascii=False)}\n\n"
        "Analizá los motivos y dame un panorama corto de qué está pasando."
    )

    # ────────────────────────────────────────────────────────────────
    # Inspección de qué delegó el supervisor
    # ────────────────────────────────────────────────────────────────
    section("DELEGACIONES QUE HIZO EL SUPERVISOR")
    tool_calls = loop.history.by_type("tool_call")
    for tc in tool_calls:
        nombre = tc.content.get("name")
        args = tc.content.get("arguments") or {}
        preview = list(args.keys())
        print(f"  - paso {tc.content.get('turn_num')}: {nombre}({preview})")

    # Con `stop_tool`, el panorama final viene en el argumento de la
    # llamada a `entregar_panorama_final`. Lo extraemos de ahí.
    section("PANORAMA FINAL DEL SUPERVISOR")
    panorama = ""
    for tc in tool_calls:
        if tc.content.get("name") == "entregar_panorama_final":
            panorama = (tc.content.get("arguments") or {}).get("panorama_md", "")
            break
    print(panorama)

    section("ESTADÍSTICAS DEL RUN")
    print(f"  total_steps          : {result.total_steps}")
    print(f"  delegaciones (tools) : {len(tool_calls)}")
    print(f"  terminated_reason    : {result.terminated_reason}")

    # ────────────────────────────────────────────────────────────────
    # Verificación mínima — el supervisor delegó algo y entregó panorama
    # ────────────────────────────────────────────────────────────────
    assert len(tool_calls) >= 1, "El supervisor tendría que haber delegado al menos una vez"
    assert panorama, "El supervisor debería haber producido un panorama final"

    print("\n✅ Ejemplo 20 completado correctamente.")


if __name__ == "__main__":
    main()
