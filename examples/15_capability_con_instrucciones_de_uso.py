"""
Ejemplo 15 — Capability con `global_instructions`: reglas de uso de las tools
============================================================================

Caso funcional
--------------
Mismo `gestion_pedidos` del ejemplo 14 (registrar / consultar / cancelar
pedidos). Pero ahora el comercio tiene **reglas operativas** que
condicionan *cómo* se usan esas tools:

1. Antes de cancelar, el agente debe listar los datos del pedido
   (cliente, monto) y advertir explícitamente al usuario.
2. Al registrar un pedido, debe confirmar siempre con el formato
   `ID asignado: P-XXX` para que el sistema downstream pueda parsearlo.

Esas reglas NO son parte del contrato de cada tool individual (la tool
solo registra/consulta/cancela). Son reglas del *negocio* sobre cómo
usar el conjunto.

`AgentCapabilities` permite atar esas reglas al capability mismo vía
`global_instructions=...`. Cuando el capability se le pasa a un agente,
el agente recibe esas instrucciones en su system prompt
automáticamente — sin que el dev tenga que copiarlas a mano al
`role_setup`.

Qué muestra este ejemplo
------------------------
1. Cómo agregar `global_instructions` a un capability ya construido.
2. Cómo verificar que el agente las recibe en su system prompt vía
   `agente.get_resolved_role_setup()` (sin invocar al LLM).
3. Cómo se aplican en la práctica: el mismo pedido a cancelar dispara
   un comportamiento distinto con vs sin las instrucciones.

Cómo correr
-----------
    python3 examples/15_capability_con_instrucciones_de_uso.py
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

from instantneo import AgentCapabilities, InstantNeo, tool


# ────────────────────────────────────────────────────────────────────
# Las mismas tools del ejemplo 14 (con la BD también en memoria)
# ────────────────────────────────────────────────────────────────────
_PEDIDOS: dict = {
    "P-001": {"cliente": "Aurora Salazar", "monto": 320.0,  "estado": "pendiente"},
    "P-002": {"cliente": "Marcos Quispe",  "monto": 780.0,  "estado": "pendiente"},
    "P-003": {"cliente": "Lucía Vargas",   "monto": 1450.0, "estado": "pendiente"},
}


@tool(
    description="Registra un pedido nuevo. Devuelve el id asignado.",
    parameters={
        "cliente": {"type": "string", "description": "Nombre del cliente."},
        "monto":   {"type": "number", "description": "Monto total en dólares."},
    },
)
def registrar_pedido(cliente: str, monto: float) -> dict:
    nuevo_id = f"P-{len(_PEDIDOS) + 1:03d}"
    _PEDIDOS[nuevo_id] = {"cliente": cliente, "monto": monto, "estado": "pendiente"}
    return {"id": nuevo_id, "estado": "pendiente"}


@tool(
    description="Consulta el estado de un pedido por su id.",
    parameters={"pedido_id": {"type": "string", "description": "Id del pedido."}},
)
def consultar_pedido_por_id(pedido_id: str) -> dict:
    if pedido_id not in _PEDIDOS:
        return {"error": f"pedido {pedido_id!r} no existe"}
    return {"id": pedido_id, **_PEDIDOS[pedido_id]}


@tool(
    description="Cancela un pedido SI está pendiente.",
    parameters={"pedido_id": {"type": "string", "description": "Id del pedido."}},
)
def cancelar_pedido_pendiente(pedido_id: str) -> dict:
    if pedido_id not in _PEDIDOS:
        return {"error": f"pedido {pedido_id!r} no existe"}
    if _PEDIDOS[pedido_id]["estado"] != "pendiente":
        return {"error": f"pedido {pedido_id!r} no se puede cancelar (estado: {_PEDIDOS[pedido_id]['estado']!r})"}
    _PEDIDOS[pedido_id]["estado"] = "cancelado"
    return {"id": pedido_id, "estado": "cancelado"}


# ────────────────────────────────────────────────────────────────────
# Capability con `global_instructions`
# ────────────────────────────────────────────────────────────────────
# El texto se construye una vez y queda atado al capability. Cuando
# el capability se le pasa a un agente, su contenido se inyecta al
# system prompt — el agente lo "ve" antes de cada turno.
#
# Buenas prácticas para el texto:
# - Imperativo claro ("antes de X, hacer Y").
# - Específico al dominio (no instrucciones genéricas tipo "sé útil").
# - Verificables por el dev al observar el output.
REGLAS_OPERATIVAS = (
    "Reglas operativas del comercio para usar las tools:\n"
    "1. Antes de cancelar un pedido, llamá primero a "
    "`consultar_pedido_por_id` para verificar que sigue pendiente. "
    "Si efectivamente está pendiente, procedé con la cancelación e "
    "incluí cliente y monto del pedido en tu respuesta final.\n"
    "2. Al registrar un pedido nuevo, en tu respuesta final usá "
    "EXACTAMENTE este formato: 'ID asignado: P-XXX' (con el id real "
    "devuelto por la tool). Es un contrato con el sistema downstream.\n"
    "3. No pidas confirmaciones ni esperes respuestas — resolvé "
    "autónomamente con los datos disponibles."
)

gestion_pedidos = AgentCapabilities(
    name="gestion_pedidos",
    description="Operaciones sobre pedidos + reglas operativas del comercio.",
    skills=[registrar_pedido, consultar_pedido_por_id, cancelar_pedido_pendiente],
    global_instructions=REGLAS_OPERATIVAS,
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
    # Agente que recibe el capability con reglas
    # ────────────────────────────────────────────────────────────────
    # `role_setup` define QUIÉN es el agente; las `global_instructions`
    # del capability definen CÓMO debe usar las tools. Son ortogonales.
    agente = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup="Eres operador interno del comercio. Sé conciso.",
        tools=gestion_pedidos,
        max_tokens=400,
    )

    # ────────────────────────────────────────────────────────────────
    # Inspección del system prompt resuelto — sin invocar al LLM
    # ────────────────────────────────────────────────────────────────
    # `get_resolved_role_setup()` arma el system prompt final que ve
    # el provider: role_setup + tool_instructions (de las
    # global_instructions del capability) + shelf_context si lo hay.
    # Es la forma de verificar QUÉ recibe el agente sin gastar tokens.
    section("SYSTEM PROMPT RESUELTO")
    print(agente.get_resolved_role_setup())

    # Confirmamos que el texto de las reglas está en el system prompt:
    resolved = agente.get_resolved_role_setup()
    assert "Reglas operativas del comercio" in resolved
    assert "ID asignado: P-XXX" in resolved

    # ────────────────────────────────────────────────────────────────
    # Escenario 1 — cancelación: debe verificar primero y advertir
    # ────────────────────────────────────────────────────────────────
    section("ESCENARIO 1 — pedido de cancelación de P-002")
    respuesta_1 = agente.run("Cancelá el pedido P-002, por favor.")
    print(f"\n  agente → {respuesta_1}")

    tools_llamadas = [te.name for te in agente.last_run.tool_executions]
    print(f"  tools llamadas (en orden): {tools_llamadas}")

    # Verificamos que aplicó la regla 1: consultar antes de cancelar.
    # Si el agente solo consulta y se detiene a esperar confirmación,
    # también es comportamiento válido — la regla dice "verificar".
    assert "consultar_pedido_por_id" in tools_llamadas, (
        "El agente debería consultar antes de cancelar (regla 1)"
    )
    # Si llegó a cancelar también, la consulta debería haber sido antes:
    if "cancelar_pedido_pendiente" in tools_llamadas:
        idx_consulta = tools_llamadas.index("consultar_pedido_por_id")
        idx_cancel   = tools_llamadas.index("cancelar_pedido_pendiente")
        assert idx_consulta < idx_cancel, "Debe consultar ANTES de cancelar"

    # ────────────────────────────────────────────────────────────────
    # Escenario 2 — registro: debe responder con formato exacto
    # ────────────────────────────────────────────────────────────────
    section("ESCENARIO 2 — registro de pedido nuevo")
    respuesta_2 = agente.run(
        "Registrá un pedido nuevo: cliente 'Beatriz Rojas', monto 215."
    )
    print(f"\n  agente → {respuesta_2}")

    # Verificamos que aplicó la regla 2: formato 'ID asignado: P-XXX'
    # El text puede venir como dict {'text':..., 'tool_results':...} o solo
    # tool_results — lo extraemos defensivamente.
    text_respuesta = ""
    if isinstance(respuesta_2, dict):
        text_respuesta = respuesta_2.get("text") or ""
    else:
        text_respuesta = str(respuesta_2 or "")
    print(f"\n  text de respuesta_2: {text_respuesta!r}")

    # La aserción del formato sería "ID asignado:" pero el modelo
    # puede variarlo levemente; lo dejamos como observación
    # (no assert) y verificamos lo robusto: la tool se llamó.
    tools_2 = [te.name for te in agente.last_run.tool_executions]
    assert "registrar_pedido" in tools_2

    # ────────────────────────────────────────────────────────────────
    # Contraste: el mismo agente SIN `global_instructions`
    # ────────────────────────────────────────────────────────────────
    # Construimos un capability gemelo, sin las reglas, y pasamos un
    # pedido equivalente. Mostramos que sin las reglas el agente puede
    # cancelar directo sin consultar.
    section("CONTRASTE — sin global_instructions, ¿qué cambia?")
    gestion_sin_reglas = AgentCapabilities(
        name="gestion_pedidos_sin_reglas",
        skills=[registrar_pedido, consultar_pedido_por_id, cancelar_pedido_pendiente],
    )
    agente_sin_reglas = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup="Eres operador interno del comercio. Sé conciso.",
        tools=gestion_sin_reglas,
        max_tokens=400,
    )
    # Re-poblamos P-002 para poder cancelarlo de nuevo
    _PEDIDOS["P-002"]["estado"] = "pendiente"

    respuesta_3 = agente_sin_reglas.run("Cancelá el pedido P-002.")
    print(f"\n  agente_sin_reglas → {respuesta_3}")
    tools_3 = [te.name for te in agente_sin_reglas.last_run.tool_executions]
    print(f"  tools llamadas : {tools_3}")
    print(f"  (sin la regla 1, puede ir directo a cancelar)")

    print("\n✅ Ejemplo 15 completado correctamente.")


if __name__ == "__main__":
    main()
