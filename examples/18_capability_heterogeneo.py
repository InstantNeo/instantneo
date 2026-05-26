"""
Ejemplo 18 — Capability heterogéneo: tools + skill SKILL.md + sub-capability + prompt
======================================================================================

Caso funcional
--------------
El comercio tiene un agente de "análisis contable" que necesita varias
cosas a la vez para producir su trabajo:

- **Tools directas propias** del contexto: `listar_movimientos_del_mes`
  para traerse los registros, `marcar_como_revisado` para confirmar que
  un movimiento pasó por revisión.
- **Una skill formal SKILL.md** de clasificación de gastos
  (`clasificar_gasto/`) — vive como una carpeta separada y reusable
  con su propio frontmatter, body y scripts. La cargamos como item
  externo y la activamos cuando hace falta.
- **Un sub-capability de utilidades de fecha** (`utilidades_fecha`) que
  agrupa pequeños helpers reusables (parsear "el mes pasado", formatear
  fechas) que también se usan en otros agentes.
- **Instrucciones globales** del capability principal que orquestan
  cómo combinar todo.

Todo eso vive en **UN solo `AgentCapabilities`**: el container es
heterogéneo por diseño. El agente lo recibe como una sola unidad.

Qué muestra este ejemplo
------------------------
1. Construir un capability heterogéneo (tools + skill + sub-capability
   + global_instructions) ensamblando los cuatro tipos.
2. Inspeccionar la estructura desde el dev: qué hay en `.registry`,
   en `.skill_folders`, en `.managers`, y en `.global_instructions`.
3. Activar el skill SKILL.md desde el capability y observar que sus
   tools quedan disponibles para el agente.

Cómo correr
-----------
    python3 examples/18_capability_heterogeneo.py
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
# Datos sintéticos (los movimientos del mes en memoria)
# ────────────────────────────────────────────────────────────────────
_MOVIMIENTOS = [
    {"id": "M001", "fecha": "2026-05-02", "descripcion": "Alquiler oficina mayo",  "monto": 850.0, "revisado": False},
    {"id": "M002", "fecha": "2026-05-03", "descripcion": "Insumos para mercadería", "monto": 320.0, "revisado": False},
    {"id": "M003", "fecha": "2026-05-04", "descripcion": "Publicidad redes sociales", "monto": 145.0, "revisado": False},
    {"id": "M004", "fecha": "2026-05-05", "descripcion": "Comisión bancaria mensual", "monto":  18.0, "revisado": False},
    {"id": "M005", "fecha": "2026-05-08", "descripcion": "Mantenimiento heladera", "monto":  95.0, "revisado": False},
]


# ────────────────────────────────────────────────────────────────────
# Pieza 1 — dos tools directas del capability principal
# ────────────────────────────────────────────────────────────────────
@tool(
    description="Lista los movimientos contables del mes en curso.",
    parameters={},
)
def listar_movimientos_del_mes() -> list:
    return _MOVIMIENTOS


@tool(
    description="Marca un movimiento como revisado por id.",
    parameters={"movimiento_id": {"type": "string", "description": "Id del movimiento."}},
)
def marcar_como_revisado(movimiento_id: str) -> dict:
    for m in _MOVIMIENTOS:
        if m["id"] == movimiento_id:
            m["revisado"] = True
            return {"id": movimiento_id, "revisado": True}
    return {"error": f"movimiento {movimiento_id!r} no existe"}


# ────────────────────────────────────────────────────────────────────
# Pieza 2 — sub-capability `utilidades_fecha`
# ────────────────────────────────────────────────────────────────────
# Helpers que viven aparte para ser reusados por otros agentes del
# comercio. Lo construimos como un AgentCapabilities propio.
@tool(
    description="Parsea un periodo relativo ('este mes', 'mes pasado') a un dict con fecha_inicio y fecha_fin en ISO.",
    parameters={"periodo": {"type": "string", "description": "Texto del periodo, ej. 'este mes'."}},
)
def parsear_periodo_relativo(periodo: str) -> dict:
    # Implementación simplificada para la demo
    if periodo.lower() in ("este mes", "mes actual"):
        return {"periodo": periodo, "fecha_inicio": "2026-05-01", "fecha_fin": "2026-05-31"}
    if periodo.lower() in ("mes pasado", "mes anterior"):
        return {"periodo": periodo, "fecha_inicio": "2026-04-01", "fecha_fin": "2026-04-30"}
    return {"periodo": periodo, "error": "periodo no reconocido"}


@tool(
    description="Formatea una fecha ISO (YYYY-MM-DD) a 'DD de Mes YYYY' en español.",
    parameters={"fecha_iso": {"type": "string", "description": "Fecha en formato ISO."}},
)
def formatear_fecha_iso(fecha_iso: str) -> str:
    meses = ["enero","febrero","marzo","abril","mayo","junio",
             "julio","agosto","setiembre","octubre","noviembre","diciembre"]
    try:
        y, m, d = fecha_iso.split("-")
        return f"{int(d)} de {meses[int(m) - 1]} {y}"
    except Exception:
        return fecha_iso


utilidades_fecha = AgentCapabilities(
    name="utilidades_fecha",
    description="Helpers de fechas y periodos relativos.",
    skills=[parsear_periodo_relativo, formatear_fecha_iso],
)


# ────────────────────────────────────────────────────────────────────
# Pieza 3 — el capability principal HETEROGÉNEO
# ────────────────────────────────────────────────────────────────────
# Lo construimos en pasos para hacer evidente que es heterogéneo:
# 1) las tools propias del dominio,
# 2) el sub-capability `utilidades_fecha` como manager anidado,
# 3) la skill SKILL.md `clasificar_gasto/` como item formal,
# 4) las global_instructions que explican cómo se compone.
analista_contable = AgentCapabilities(
    name="analista_contable",
    description="Capability principal del agente de análisis contable mensual.",
    skills=[listar_movimientos_del_mes, marcar_como_revisado],   # ← tools propias
    global_instructions=(
        "Sos el analista contable del comercio. Tu trabajo en cada "
        "consulta es:\n"
        "1. Traer los movimientos del mes (`listar_movimientos_del_mes`).\n"
        "2. Para cada movimiento, clasificarlo en categoría contable "
        "usando la skill `clasificar_gasto` (su tool `clasificar_gasto_categoria`).\n"
        "3. Presentá el listado clasificado y un total por categoría.\n"
        "Para fechas formateadas en lenguaje natural usá las helpers "
        "del sub-capability `utilidades_fecha`."
    ),
)

# Sub-capability como manager anidado
analista_contable.load_skills.from_manager(utilidades_fecha)

# Skill SKILL.md como item formal — se carga (no se activa todavía)
SKILL_FOLDER = _REPO_ROOT / "examples" / "skill_md_demos" / "clasificar_gasto"
analista_contable.load_skills.from_skill_folder(str(SKILL_FOLDER))


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
    # Estructura interna del capability heterogéneo
    # ────────────────────────────────────────────────────────────────
    # Cuatro tipos de elemento conviven en el mismo objeto:
    section("INSPECCIÓN DE `analista_contable` — qué hay dentro")
    print(f"  tools propias (.registry)        : {analista_contable.get_tool_names()}")
    print(f"  sub-capabilities (.managers)     : {list(analista_contable.managers.keys())}")
    print(f"  skills SKILL.md (.skill_folders) : {list(analista_contable.skill_folders.keys())}")
    print(f"  global_instructions chars        : {len(analista_contable.get_global_instructions())}")

    assert "listar_movimientos_del_mes" in analista_contable.get_tool_names()
    assert "marcar_como_revisado" in analista_contable.get_tool_names()
    assert "utilidades_fecha" in analista_contable.managers
    assert "clasificar_gasto" in analista_contable.skill_folders

    # ────────────────────────────────────────────────────────────────
    # Qué ve el agente "out of the box" — antes de activar la skill
    # ────────────────────────────────────────────────────────────────
    # Las tools que el agente recibe son las directamente registradas
    # en el capability. La skill SKILL.md está cargada pero NO activa:
    # sus tools (los scripts) NO se inyectan hasta que alguien
    # (el dev o el propio agente vía nav tools) la active.
    section("DISCOVERY — qué expone `discover()` al agente o al dev")
    descubrimientos = analista_contable.discover()
    for d in descubrimientos:
        print(f"  - [{d.get('type'):<13}] {d.get('name')}: {d.get('description', '')[:70]}")

    # ────────────────────────────────────────────────────────────────
    # Activación del skill SKILL.md → sus tools se vuelven disponibles
    # ────────────────────────────────────────────────────────────────
    # `activate(name)` registra los scripts del skill como tools del
    # capability padre, e inyecta el body del SKILL.md como contexto
    # del item activo. Después de esto, el agente "ve" la tool de
    # clasificación.
    section("ACTIVAR skill `clasificar_gasto`")
    resultado_activacion = analista_contable.activate("clasificar_gasto")
    print(f"  activated: {resultado_activacion.get('name')} ({resultado_activacion.get('type')})")
    print(f"  description: {resultado_activacion.get('description', '')[:80]}")
    print(f"  tools cargadas: {resultado_activacion.get('skills_loaded', [])}")

    print(f"\n  tools totales del capability tras activar:")
    print(f"  → {analista_contable.get_tool_names()}")
    assert "clasificar_gasto_categoria" in analista_contable.get_tool_names()

    # ────────────────────────────────────────────────────────────────
    # Agente que recibe el capability heterogéneo y trabaja
    # ────────────────────────────────────────────────────────────────
    # Nota: las tools del sub-capability `utilidades_fecha` también
    # están disponibles para el agente porque al pasar capabilities
    # como manager, sus tools no se inyectan automáticamente al
    # padre — para que el agente las use hay que registrarlas o
    # activarlas. En este ejemplo las dejamos disponibles pasando
    # `utilidades_fecha` junto al principal como otra capability del
    # agente.
    agente = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup="Eres analista contable mensual del comercio.",
        tools=[analista_contable, utilidades_fecha],
        max_tokens=800,
    )

    section("AGENTE — tools disponibles en su capability final")
    print(f"  {agente.get_tool_names()}")
    nombres_agente = set(agente.get_tool_names())
    # Tools propias del principal + tool del skill activado + tools del sub-cap
    assert "listar_movimientos_del_mes" in nombres_agente
    assert "marcar_como_revisado" in nombres_agente
    assert "clasificar_gasto_categoria" in nombres_agente
    assert "parsear_periodo_relativo" in nombres_agente
    assert "formatear_fecha_iso" in nombres_agente

    # ────────────────────────────────────────────────────────────────
    # Corrida real con un loop (necesita varios pasos)
    # ────────────────────────────────────────────────────────────────
    loop = InstantLoop(
        agent=agente, history=History(),
        name="loop_analista_contable", max_steps=10,
    )
    section("CORRIDA — analista produce listado clasificado del mes")
    result = loop.run(
        "Hacé el análisis contable del mes en curso: listame los "
        "movimientos clasificados por categoría y dame el total por "
        "categoría."
    )

    # Tomamos la primera respuesta sustancial (con totales o el listado)
    responses = loop.history.by_type("response")
    reporte = next(
        (
            r.content.get("text")
            for r in responses
            if r.content.get("text") and any(c in r.content.get("text", "").lower()
                                              for c in ["administrativo", "operativo", "total"])
        ),
        "",
    )
    print(reporte)

    # ────────────────────────────────────────────────────────────────
    # Verificación: el agente combinó las tres fuentes de tools
    # ────────────────────────────────────────────────────────────────
    tools_usadas = {tc.content.get("name") for tc in loop.history.by_type("tool_call")}
    print(f"\n  tools usadas a lo largo del loop: {sorted(tools_usadas)}")
    assert "listar_movimientos_del_mes" in tools_usadas, "Debe traer los movimientos"
    assert "clasificar_gasto_categoria" in tools_usadas, "Debe clasificar usando la skill"

    print("\n✅ Ejemplo 18 completado correctamente.")


if __name__ == "__main__":
    main()
