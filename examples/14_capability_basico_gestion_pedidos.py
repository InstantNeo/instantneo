"""
Ejemplo 14 — Capability básico: agrupar tools en `AgentCapabilities`
=====================================================================

Léxico que vamos a usar de acá en adelante
------------------------------------------
La librería distingue tres cosas que a veces se confunden:

- **`tool`**: una función Python decorada con `@tool(...)`. Ejecutable.
- **`skill`**: una **carpeta** con `SKILL.md` adentro, siguiendo el
  estándar Agent Skills (https://agentskills.io). Lo vemos en el
  ejemplo 19.
- **`AgentCapabilities`**: un **contenedor** que agrupa tools + skills
  + sub-capabilities + instrucciones de uso. Es la pieza vigente para
  empaquetar funcionalidad y dársela a un agente.

(Existen alias backward-compat: `SkillManager` para `AgentCapabilities`,
`@skill` para `@tool`, etc. En código nuevo, usamos los nombres vigentes.
El parámetro `skills=` del constructor de `AgentCapabilities` recibe
funciones `@tool` y se llama así por compatibilidad histórica.)

Caso funcional
--------------
Comercio mediano que gestiona pedidos. Tres operaciones:

1. registrar un pedido nuevo
2. consultar un pedido por id
3. cancelar un pedido pendiente

Queremos exponer estas operaciones a dos agentes distintos:

- **`agente_atencion`**: rol read-only, atiende a clientes. Solo debería
  *consultar* el estado.
- **`agente_operacion`**: rol interno, puede registrar y cancelar.

La pregunta de diseño: ¿definimos las mismas tools dos veces? ¿Filtramos
manualmente al crear cada agente? Acá vamos a ver el patrón limpio:
**un solo `AgentCapabilities` reusable**, y el `role_setup` de cada
agente decide qué hace con esas tools disponibles.

Qué muestra este ejemplo
------------------------
1. Cómo agrupar funciones con `@tool` en un `AgentCapabilities`.
2. Por qué un capability es más reusable que pasar `tools=[fn1, fn2]`
   directo: el mismo objeto se pasa a varios agentes sin re-importar.
3. Cómo el `role_setup` del agente decide el comportamiento aunque
   el capability exponga más operaciones.

Cómo correr
-----------
    python3 examples/14_capability_basico_gestion_pedidos.py
"""
import datetime
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
# "Base de datos" en memoria — simulamos persistencia mínima
# ────────────────────────────────────────────────────────────────────
# El estado vive en este dict para que las tools tengan algo concreto
# que tocar. En un sistema real esto sería una BD/API.
_PEDIDOS: dict = {
    "P-001": {"cliente": "Aurora Salazar", "monto": 320.0, "estado": "pendiente"},
    "P-002": {"cliente": "Marcos Quispe",  "monto": 780.0, "estado": "pendiente"},
    "P-003": {"cliente": "Lucía Vargas",   "monto": 145.0, "estado": "entregado"},
}


# ────────────────────────────────────────────────────────────────────
# Las tres tools — funciones planas con `@tool`
# ────────────────────────────────────────────────────────────────────
# Cada una expone su contrato vía `description` y `parameters`.
# Eso es lo que ve el LLM cuando elige qué tool llamar.

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
    return {"id": nuevo_id, "estado": "pendiente", "creado_en": datetime.datetime.now().isoformat(timespec="seconds")}


@tool(
    description="Consulta el estado de un pedido por su id.",
    parameters={
        "pedido_id": {"type": "string", "description": "Id del pedido, formato P-NNN."},
    },
)
def consultar_pedido_por_id(pedido_id: str) -> dict:
    if pedido_id not in _PEDIDOS:
        return {"error": f"pedido {pedido_id!r} no existe"}
    return {"id": pedido_id, **_PEDIDOS[pedido_id]}


@tool(
    description=(
        "Cancela un pedido SI está en estado pendiente. Si ya fue "
        "entregado o cancelado, devuelve error."
    ),
    parameters={
        "pedido_id": {"type": "string", "description": "Id del pedido."},
    },
)
def cancelar_pedido_pendiente(pedido_id: str) -> dict:
    if pedido_id not in _PEDIDOS:
        return {"error": f"pedido {pedido_id!r} no existe"}
    if _PEDIDOS[pedido_id]["estado"] != "pendiente":
        return {"error": f"pedido {pedido_id!r} no se puede cancelar (estado: {_PEDIDOS[pedido_id]['estado']!r})"}
    _PEDIDOS[pedido_id]["estado"] = "cancelado"
    return {"id": pedido_id, "estado": "cancelado"}


# ────────────────────────────────────────────────────────────────────
# Capability `gestion_pedidos` — reúne las 3 tools en un solo objeto
# ────────────────────────────────────────────────────────────────────
# `name` y `description` son metadata del capability mismo (no de cada
# tool). Sirven cuando el capability se usa dentro de un shelf o como
# sub-capability — el dev y el agente lo identifican por ahí.
#
# `skills=[...]` es el parámetro histórico para inyectar tools en la
# construcción. Recibe funciones decoradas con `@tool`.
gestion_pedidos = AgentCapabilities(
    name="gestion_pedidos",
    description="Operaciones básicas sobre el catálogo de pedidos del comercio.",
    skills=[registrar_pedido, consultar_pedido_por_id, cancelar_pedido_pendiente],
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
    # Equivalencia con la vía "lista de funciones"
    # ────────────────────────────────────────────────────────────────
    # Históricamente, le pasás al agente la lista cruda:
    #     InstantNeo(..., tools=[fn1, fn2, fn3])
    # Internamente, el agente crea su propio `AgentCapabilities` y
    # registra las tools. Esa vía funciona, pero el capability no es
    # reusable: queda escondido adentro del agente.
    #
    # Con un capability explícito definido afuera, podemos pasárselo a
    # cualquier cantidad de agentes sin redefinir nada.
    section("CAPABILITY DEFINIDO")
    print(f"  name        : {gestion_pedidos.name}")
    print(f"  description : {gestion_pedidos.description}")
    print(f"  tools       : {gestion_pedidos.get_tool_names()}")

    # ────────────────────────────────────────────────────────────────
    # Mismo capability → dos agentes con distinta autoridad
    # ────────────────────────────────────────────────────────────────
    # El capability NO contiene autorización. Quien decide qué hacer es
    # el `role_setup` del agente. Acá los dos agentes ven exactamente
    # las mismas 3 tools, pero las usan distinto.

    agente_atencion = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup=(
            "Eres atención al cliente de un comercio. Tu trabajo es "
            "responder consultas sobre pedidos de los clientes. "
            "NUNCA registres pedidos nuevos ni canceles nada — solo "
            "consulta. Si te piden hacer otra cosa, explicá que tenés "
            "que derivar al área de operaciones."
        ),
        tools=gestion_pedidos,   # pasamos el capability como objeto
        max_tokens=400,
    )

    agente_operacion = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup=(
            "Eres operador interno del comercio. Podés registrar, "
            "consultar y cancelar pedidos. Sé breve y reportá cada "
            "acción con el id correspondiente."
        ),
        tools=gestion_pedidos,   # MISMO objeto, no una copia
        max_tokens=400,
    )

    # Sanity check: ambos agentes ven las mismas 3 tools
    section("TOOLS DISPONIBLES POR AGENTE")
    print(f"  agente_atencion  : {agente_atencion.get_tool_names()}")
    print(f"  agente_operacion : {agente_operacion.get_tool_names()}")
    assert agente_atencion.get_tool_names() == agente_operacion.get_tool_names()

    # ────────────────────────────────────────────────────────────────
    # Ejecución: el role_setup gobierna el comportamiento
    # ────────────────────────────────────────────────────────────────
    section("ESCENARIO 1 — cliente le pregunta a `agente_atencion` por P-001")
    respuesta_1 = agente_atencion.run(
        "Hola, soy el cliente del pedido P-001, ¿podrías decirme el estado?"
    )
    print(f"\n  agente_atencion → {respuesta_1}")

    # Inspeccionamos las tools que llamó: esperamos `consultar_pedido_por_id`
    tools_usadas_atencion = [te.name for te in agente_atencion.last_run.tool_executions]
    print(f"  tools llamadas : {tools_usadas_atencion}")

    section("ESCENARIO 2 — operación quiere cancelar P-002")
    respuesta_2 = agente_operacion.run(
        "Necesitamos cancelar el pedido P-002 — el cliente desistió."
    )
    print(f"\n  agente_operacion → {respuesta_2}")
    tools_usadas_operacion = [te.name for te in agente_operacion.last_run.tool_executions]
    print(f"  tools llamadas : {tools_usadas_operacion}")

    # Estado final de la "BD" para confirmar que la acción se hizo
    section("ESTADO DE LOS PEDIDOS POST-RUN")
    for pid, datos in _PEDIDOS.items():
        print(f"  {pid}: {datos}")

    # ────────────────────────────────────────────────────────────────
    # Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    # No usamos asserts duros sobre el comportamiento del LLM (puede
    # variar entre runs), pero sí confirmamos lo esencial:
    # - el agente_atencion al menos consultó (no cancelar ni registrar)
    # - el agente_operacion usó la cancelación, y P-002 quedó cancelado
    assert "registrar_pedido" not in tools_usadas_atencion
    assert "cancelar_pedido_pendiente" not in tools_usadas_atencion
    assert _PEDIDOS["P-002"]["estado"] == "cancelado"

    print("\n✅ Ejemplo 14 completado correctamente.")


if __name__ == "__main__":
    main()
