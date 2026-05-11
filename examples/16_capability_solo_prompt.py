"""
Ejemplo 16 — Capability solo-prompt: agrupar instrucciones sin tools
=====================================================================

Caso funcional
--------------
Un comercio quiere que **todos** sus agentes que producen reportes
(ventas, inventario, marketing, finanzas) usen exactamente el mismo
formato cuando responden con un reporte ejecutivo:

    ## Resumen
    ...
    ## Hallazgos
    ...
    ## Acciones recomendadas
    ...

La regla NO involucra tools — es solo una plantilla de salida. Definirla
en cada `role_setup` individual es duplicación: si cambia el formato,
hay que tocar N agentes.

`AgentCapabilities` no obliga a tener tools. Un capability con
`global_instructions` y **cero tools** es un "prompt-pack reutilizable":
el formato vive en un solo lugar y se inyecta a cualquier agente que lo
reciba.

Qué muestra este ejemplo
------------------------
1. Cómo construir un `AgentCapabilities` solo con `global_instructions`.
2. Cómo combinarlo con un capability de tools (vía `tools=[c1, c2]`).
3. Que dos agentes distintos (uno de ventas, otro de inventario) que
   reciben el mismo prompt-pack producen reportes con la misma
   estructura.

Cómo correr
-----------
    python3 examples/16_capability_solo_prompt.py
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

from instantneo import AgentCapabilities, History, InstantLoop, InstantNeo, tool


# ────────────────────────────────────────────────────────────────────
# Datos sintéticos para que las tools tengan algo que devolver
# ────────────────────────────────────────────────────────────────────
_VENTAS_DEL_MES = [
    {"producto": "mate listo",       "unidades": 42, "ingreso": 504.0},
    {"producto": "yerba kg",         "unidades": 67, "ingreso": 871.0},
    {"producto": "termo acero 1L",   "unidades":  8, "ingreso": 480.0},
    {"producto": "bombilla pico de loro", "unidades": 15, "ingreso": 225.0},
]

_STOCK_ACTUAL = {
    "yerba kg":      {"stock": 12, "minimo": 50, "estado": "crítico"},
    "mate listo":    {"stock": 35, "minimo": 20, "estado": "ok"},
    "termo acero 1L": {"stock":  3, "minimo": 10, "estado": "crítico"},
    "bombilla pico de loro": {"stock": 28, "minimo": 15, "estado": "ok"},
}


# ────────────────────────────────────────────────────────────────────
# Tools de dos dominios distintos — viven en capabilities separados
# ────────────────────────────────────────────────────────────────────

@tool(
    description="Devuelve las ventas del mes en curso, por producto.",
    parameters={},
)
def consultar_ventas_del_mes() -> list:
    return _VENTAS_DEL_MES


@tool(
    description="Devuelve los productos con stock por debajo de su mínimo.",
    parameters={},
)
def consultar_stock_critico() -> list:
    return [
        {"producto": p, **d}
        for p, d in _STOCK_ACTUAL.items()
        if d["estado"] == "crítico"
    ]


capabilities_ventas = AgentCapabilities(
    name="consulta_ventas",
    description="Tools para consultar ventas del comercio.",
    skills=[consultar_ventas_del_mes],
)

capabilities_inventario = AgentCapabilities(
    name="consulta_inventario",
    description="Tools para consultar el stock del comercio.",
    skills=[consultar_stock_critico],
)


# ────────────────────────────────────────────────────────────────────
# Capability puro prompt — sin tools, solo formato de salida
# ────────────────────────────────────────────────────────────────────
# Reusable por cualquier agente que produzca reportes. Si mañana se
# decide agregar una sección "Anexo de datos", se cambia acá una sola
# vez y todos los agentes la respetan.
PLANTILLA_REPORTE = (
    "Formato obligatorio para reportes ejecutivos:\n\n"
    "Tu respuesta debe estructurarse en Markdown con exactamente "
    "estas tres secciones, en este orden:\n\n"
    "## Resumen\n"
    "Un párrafo corto (2-3 líneas) describiendo el panorama general.\n\n"
    "## Hallazgos\n"
    "Bullets concretos con los datos clave que justifican el resumen.\n\n"
    "## Acciones recomendadas\n"
    "Bullets accionables con verbo imperativo al inicio (revisar X, "
    "ajustar Y, escalar Z).\n\n"
    "No agregues secciones extras ni preámbulos antes de '## Resumen'."
)

formato_reportes = AgentCapabilities(
    name="formato_reportes_ejecutivos",
    description="Plantilla de salida estandarizada para reportes ejecutivos. Sin tools.",
    global_instructions=PLANTILLA_REPORTE,
    # Notá: sin `skills=`. Es un capability vacío de tools.
)


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
    section("CAPABILITY SOLO-PROMPT — qué hay adentro")
    print(f"  name                : {formato_reportes.name}")
    print(f"  tools registradas   : {formato_reportes.get_tool_names()}")
    print(f"  global_instructions : {len(formato_reportes.get_global_instructions())} chars")
    # Cero tools, solo prompt:
    assert formato_reportes.get_tool_names() == []
    assert len(formato_reportes.get_global_instructions()) > 0

    # ────────────────────────────────────────────────────────────────
    # Dos agentes con DOMINIOS distintos pero el MISMO prompt-pack
    # ────────────────────────────────────────────────────────────────
    # Cada agente recibe una LISTA de capabilities:
    # - el capability de su dominio (con sus tools)
    # - el capability puro prompt (con el formato)
    # Internamente, InstantNeo hace `union` de ambos: el agente termina
    # con las tools del primero y las `global_instructions` concatenadas.
    agente_ventas = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup="Eres analista de ventas del comercio.",
        tools=[capabilities_ventas, formato_reportes],   # lista de capabilities
        max_tokens=500,
    )

    agente_inventario = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup="Eres analista de inventario del comercio.",
        tools=[capabilities_inventario, formato_reportes],   # mismo prompt-pack
        max_tokens=500,
    )

    # Inspección: las instrucciones de la plantilla quedaron inyectadas
    # en AMBOS system prompts.
    section("VERIFICACIÓN — ambos agentes tienen la plantilla")
    assert "Resumen" in agente_ventas.get_resolved_role_setup()
    assert "Hallazgos" in agente_ventas.get_resolved_role_setup()
    assert "Acciones recomendadas" in agente_ventas.get_resolved_role_setup()
    assert "Resumen" in agente_inventario.get_resolved_role_setup()
    print("  agente_ventas      → contiene la plantilla ✓")
    print("  agente_inventario  → contiene la plantilla ✓")

    # Cada agente conserva las tools de su propio dominio:
    print(f"\n  agente_ventas      tools: {agente_ventas.get_tool_names()}")
    print(f"  agente_inventario  tools: {agente_inventario.get_tool_names()}")
    assert agente_ventas.get_tool_names() == ["consultar_ventas_del_mes"]
    assert agente_inventario.get_tool_names() == ["consultar_stock_critico"]

    # ────────────────────────────────────────────────────────────────
    # Corrida real — los dos reportes deberían tener la misma forma
    # ────────────────────────────────────────────────────────────────
    # Para generar reporte, el agente necesita dos turnos: (1) llamar
    # a la tool y (2) producir el texto formateado. `agent.run()` hace
    # solo un turno; usamos `InstantLoop` con max_steps=3 para que
    # complete el ciclo y termine cuando produzca texto sin tool calls.
    loop_ventas = InstantLoop(
        agent=agente_ventas,
        history=History(),
        name="loop_ventas",
        max_steps=6,
    )
    loop_inv = InstantLoop(
        agent=agente_inventario,
        history=History(),
        name="loop_inventario",
        max_steps=6,
    )

    section("REPORTE 1 — ventas")
    result_ventas = loop_ventas.run(
        "Necesito el reporte ejecutivo de ventas del mes en curso."
    )
    # Tomamos el último texto producido por el agente
    responses_v = loop_ventas.history.by_type("response")
    texto_ventas = next(
        (r.content.get("text") for r in reversed(responses_v) if r.content.get("text")),
        "",
    )
    print(texto_ventas)

    section("REPORTE 2 — inventario")
    result_inv = loop_inv.run(
        "Necesito el reporte ejecutivo de productos con stock crítico."
    )
    responses_i = loop_inv.history.by_type("response")
    texto_inv = next(
        (r.content.get("text") for r in reversed(responses_i) if r.content.get("text")),
        "",
    )
    print(texto_inv)

    # ────────────────────────────────────────────────────────────────
    # Verificación: ambos respetaron las 3 secciones de la plantilla
    # ────────────────────────────────────────────────────────────────
    section("VERIFICACIÓN ESTRUCTURAL DE LOS DOS REPORTES")
    for nombre, texto in [("ventas", texto_ventas), ("inventario", texto_inv)]:
        tiene = {
            "## Resumen": "## Resumen" in (texto or ""),
            "## Hallazgos": "## Hallazgos" in (texto or ""),
            "## Acciones recomendadas": "## Acciones recomendadas" in (texto or ""),
        }
        print(f"  {nombre}: {tiene}")
        for header, presente in tiene.items():
            assert presente, f"Reporte de {nombre} no incluye {header!r}"

    print("\n✅ Ejemplo 16 completado correctamente.")


if __name__ == "__main__":
    main()
