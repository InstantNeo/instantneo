"""
Ejemplo 17 — Componer varios capabilities en un mismo agente
=============================================================

Caso funcional
--------------
Un asistente operativo del comercio necesita varias áreas a la vez:
puede consultar pedidos, consultar inventario, y debe responder con
formato estandarizado cuando produce un reporte ejecutivo.

Cada área ya vive en su propio `AgentCapabilities` (definido en otros
módulos, reusado por otros agentes). En vez de fusionarlos manualmente
ni redefinir las tools, le pasamos los tres capabilities al agente
**como lista**:

    InstantNeo(..., tools=[gestion_pedidos, consulta_inventario, formato_reportes])

Internamente la librería hace la unión: el agente termina con todas
las tools disponibles y las `global_instructions` concatenadas.

Qué muestra este ejemplo
------------------------
1. Pasar una lista de `AgentCapabilities` al agente → union automática.
2. Verificar que las tools y las instrucciones de los tres están
   presentes en el agente final.
3. La restricción importante: NO se puede mezclar capabilities con
   funciones sueltas en la misma lista (`tools=[cap, fn]` levanta
   `TypeError`). La vía correcta es `cap.register_tool(fn)` antes.

Cómo correr
-----------
    python3 examples/17_componer_varios_capabilities.py
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
# Tres capabilities, cada uno construido localmente para que el
# ejemplo sea self-contained. En un proyecto real cada uno vive en
# su propio archivo.
# ────────────────────────────────────────────────────────────────────

# ─── 1) gestion_pedidos ─────────────────────────────────────────────
_PEDIDOS = {
    "P-001": {"cliente": "Aurora Salazar", "monto": 320.0,  "estado": "pendiente"},
    "P-002": {"cliente": "Marcos Quispe",  "monto": 780.0,  "estado": "entregado"},
    "P-003": {"cliente": "Lucía Vargas",   "monto": 1450.0, "estado": "pendiente"},
}


@tool(
    description="Lista todos los pedidos por estado (pendiente, entregado, cancelado).",
    parameters={"estado": {"type": "string", "description": "Estado a filtrar."}},
)
def listar_pedidos_por_estado(estado: str) -> list:
    return [{"id": pid, **d} for pid, d in _PEDIDOS.items() if d["estado"] == estado]


gestion_pedidos = AgentCapabilities(
    name="gestion_pedidos",
    description="Consulta de pedidos por estado.",
    skills=[listar_pedidos_por_estado],
)

# ─── 2) consulta_inventario ─────────────────────────────────────────
_STOCK = {
    "yerba kg":       {"stock": 12, "minimo": 50},
    "mate listo":     {"stock": 35, "minimo": 20},
    "termo acero 1L": {"stock":  3, "minimo": 10},
}


@tool(
    description="Devuelve productos con stock por debajo del mínimo.",
    parameters={},
)
def consultar_stock_critico() -> list:
    return [
        {"producto": p, **d}
        for p, d in _STOCK.items()
        if d["stock"] < d["minimo"]
    ]


consulta_inventario = AgentCapabilities(
    name="consulta_inventario",
    description="Consultas sobre stock de productos del comercio.",
    skills=[consultar_stock_critico],
)

# ─── 3) formato_reportes_ejecutivos (puro prompt) ──────────────────
formato_reportes = AgentCapabilities(
    name="formato_reportes_ejecutivos",
    description="Plantilla estandarizada para reportes ejecutivos.",
    global_instructions=(
        "Cuando produzcas un reporte ejecutivo, usá EXACTAMENTE esta "
        "estructura Markdown:\n\n"
        "## Resumen\nUn párrafo corto.\n\n"
        "## Hallazgos\nBullets con datos.\n\n"
        "## Acciones recomendadas\nBullets con verbo imperativo."
    ),
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
    # ────────────────────────────────────────────────────────────────
    # Composición vía lista — el agente une todo automáticamente
    # ────────────────────────────────────────────────────────────────
    agente = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup="Eres asistente operativo del comercio.",
        tools=[gestion_pedidos, consulta_inventario, formato_reportes],
        max_tokens=600,
    )

    section("CAPABILITIES ORIGINALES Y QUÉ APORTA CADA UNO")
    for cap in [gestion_pedidos, consulta_inventario, formato_reportes]:
        print(f"  • {cap.name}")
        print(f"      tools  : {cap.get_tool_names()}")
        gi = cap.get_global_instructions()
        print(f"      prompt : {('sí (' + str(len(gi)) + ' chars)') if gi else 'no'}")

    section("AGENTE COMPUESTO — qué quedó disponible")
    print(f"  tools del agente: {agente.get_tool_names()}")
    resolved = agente.get_resolved_role_setup()
    print(f"  longitud del system prompt: {len(resolved)} chars")

    # Verificaciones de la composición
    nombres = set(agente.get_tool_names())
    assert "listar_pedidos_por_estado" in nombres
    assert "consultar_stock_critico" in nombres
    assert "Resumen" in resolved
    assert "Acciones recomendadas" in resolved

    # ────────────────────────────────────────────────────────────────
    # Restricción: lista MIXTA (capability + función) NO funciona
    # ────────────────────────────────────────────────────────────────
    # La librería decide la rama de inicialización mirando si TODOS los
    # items de la lista son capabilities o si TODOS son callables. La
    # mezcla levanta TypeError porque no hay forma "limpia" de unir.
    section("RESTRICCIÓN — lista mixta capability + función NO funciona")

    @tool(description="Pinea un producto como destacado.", parameters={"producto": {"type": "string"}})
    def pinear_producto(producto: str) -> dict:
        return {"producto": producto, "pinned": True}

    try:
        _ = InstantNeo(
            provider=PROVIDER, model=MODEL, api_key=API_KEY,
            role_setup="Test",
            tools=[gestion_pedidos, pinear_producto],   # ← mixto: capability + función
        )
        print("  (no debería llegar acá)")
    except TypeError as e:
        print(f"  TypeError esperado: {e}")

    # ────────────────────────────────────────────────────────────────
    # Vía correcta: registrar la función al capability ANTES
    # ────────────────────────────────────────────────────────────────
    section("VÍA CORRECTA — register_tool al capability, después componer")
    gestion_pedidos.register_tool(pinear_producto)
    print(f"  gestion_pedidos.tools (tras register): {gestion_pedidos.get_tool_names()}")

    agente_v2 = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup="Eres asistente operativo del comercio.",
        tools=[gestion_pedidos, consulta_inventario, formato_reportes],
    )
    print(f"  agente_v2 tools: {agente_v2.get_tool_names()}")
    assert "pinear_producto" in agente_v2.get_tool_names()

    # ────────────────────────────────────────────────────────────────
    # Corrida real — el agente usa las tres áreas para un reporte único
    # ────────────────────────────────────────────────────────────────
    # Usamos InstantLoop porque el agente puede necesitar varios pasos
    # (consultar pedidos pendientes + consultar stock crítico + generar
    # el reporte). El Loop le da espacio para encadenar tool calls.
    section("CORRIDA — reporte que combina pedidos pendientes + stock crítico")
    loop = InstantLoop(agent=agente, history=History(), name="loop_asistente", max_steps=8)
    result = loop.run(
        "Necesito un reporte ejecutivo de fin de día: estado de pedidos "
        "pendientes y productos con stock crítico, juntos en un solo reporte."
    )

    # Tomamos la primera respuesta que contenga la plantilla (el
    # reporte propiamente dicho). Si filtráramos por "último response
    # con texto" podríamos quedarnos con una confirmación de cierre.
    responses = loop.history.by_type("response")
    reporte_final = next(
        (
            r.content.get("text")
            for r in responses
            if r.content.get("text") and "## Resumen" in r.content.get("text", "")
        ),
        "",
    )
    print(reporte_final)

    # Verificación: el reporte respetó la plantilla del capability puro prompt
    assert "## Resumen" in reporte_final
    assert "## Hallazgos" in reporte_final
    assert "## Acciones recomendadas" in reporte_final

    # Y usó ambas áreas (pedidos + stock)
    tools_usadas = [
        tc.content.get("name")
        for tc in loop.history.by_type("tool_call")
    ]
    print(f"\n  tools llamadas a lo largo del loop: {tools_usadas}")
    assert "listar_pedidos_por_estado" in tools_usadas
    assert "consultar_stock_critico" in tools_usadas

    print("\n✅ Ejemplo 17 completado correctamente.")


if __name__ == "__main__":
    main()
