"""
Ejemplo 07 — Dos agentes paritarios por dominio (sinergia)
============================================================

Caso funcional
--------------
Tienes una tarea que ningún agente solo puede resolver porque la verdad
está repartida entre dos dominios. Cada agente tiene sus propias tools,
su propia "lente", y produce hallazgos que el otro necesita. No hay
jerarquía: ninguno aprueba ni manda. Cada uno aporta lo que ve, lee lo
que el otro vio, y juntos convergen.

El ejemplo concreto: una alerta de **memoria al 95%** en `prod-app-01`.
La causa raíz no está ni solo en infra ni solo en la app — es la
**interacción** entre ambas capas. Específicamente: una fuga de file
descriptors en la app `pagos-api` que satura los recursos del servidor.

  - **Agente Infra** ve hardware/plataforma: RAM, swap, CPU, histórico.
  - **Agente App** ve aplicación: logs, métricas de servicio, conexiones.

Ninguno solo puede diagnosticar la fuga. Infra ve "memoria saturada con
crecimiento sostenido"; App ve "open files al límite y conexiones x4".
Solo combinados → "fuga de recursos en la app que mata al servidor".

Qué demuestra
-------------
1. **Dos Loops sobre el mismo History.** Ambos agentes appendean al
   mismo log. Ninguno se entera del otro por argumento — solo por leer
   el History.
2. **Coreografía paritaria con alternancia.** Bucle exterior que llama
   `loop_infra.run()` → `loop_app.run()` → repeat, hasta que alguno
   cierra con `cerrar_diagnostico`.
3. **Dos vistas distintas registradas en el mismo History.** Cada Loop
   tiene su vista. Ambas muestran los hallazgos de ambos dominios
   (porque ahí está la sinergia) pero filtran los pasos internos del
   otro (no son relevantes). Lo que cruza son **las entregas**, no los
   borradores.
4. **Monitor por loop que publica hallazgos.** Cuando el agente llama
   `compartir_hallazgo(...)`, una regla del Monitor del loop appendea
   una entry tipo `hallazgo` con `dominio` adentro. Esa es la entrega
   estructurada que el otro agente leerá.

Cómo correr
-----------
    python3 examples/07_multi_agente_paritario.py
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

from instantneo import History, InstantLoop, InstantNeo, Monitor, tool
from instantneo.history.queries import current_run_id
from instantneo.monitor.conditions import when_last_tool_called


# ────────────────────────────────────────────────────────────────────
# Datos simulados — el escenario del incidente
# ────────────────────────────────────────────────────────────────────
RECURSOS_SERVIDOR = {
    "prod-app-01": {
        "ram_total_gb": 16.0,
        "ram_usada_gb": 15.2,
        "ram_pct": 95.0,
        "swap_usada_gb": 2.1,
        "cpu_pct": 68.0,
    },
}
HISTORICO_MEMORIA = {
    "prod-app-01": [
        {"hace_h": 0, "ram_pct": 95.0},
        {"hace_h": 1, "ram_pct": 82.0},
        {"hace_h": 2, "ram_pct": 70.0},
        {"hace_h": 4, "ram_pct": 65.0},
    ],
}
LOGS_APP = {
    "pagos-api": [
        "ERROR java.lang.OutOfMemoryError: GC overhead limit exceeded",
        "ERROR Too many open files (java.net.SocketException)",
        "WARN Connection pool exhausted, queueing requests",
        "WARN Slow query detected: 4.2s on transactions table",
    ],
}
METRICAS_SERVICIO = {
    "pagos-api": {
        "response_time_p95_ms": 8000,
        "response_time_normal_ms": 1500,
        "open_connections": 2400,
        "open_connections_normal": 600,
        "error_rate_pct": 15.0,
        "error_rate_normal_pct": 2.0,
    },
}


# ────────────────────────────────────────────────────────────────────
# Tools del Agente Infra
# ────────────────────────────────────────────────────────────────────
@tool(
    description="Devuelve el estado actual de recursos del servidor.",
    parameters={"servidor": {"description": "Nombre del servidor.", "type": "string"}},
)
def consultar_recursos_servidor(servidor: str) -> dict:
    return RECURSOS_SERVIDOR.get(servidor, {"error": "servidor no encontrado"})


@tool(
    description="Devuelve la serie histórica de uso de memoria del servidor.",
    parameters={"servidor": {"description": "Nombre del servidor.", "type": "string"}},
)
def consultar_historico_memoria(servidor: str) -> list:
    return HISTORICO_MEMORIA.get(servidor, [])


# ────────────────────────────────────────────────────────────────────
# Tools del Agente App
# ────────────────────────────────────────────────────────────────────
@tool(
    description="Devuelve los últimos eventos de log de un servicio.",
    parameters={"servicio": {"description": "Nombre del servicio.", "type": "string"}},
)
def consultar_logs_aplicacion(servicio: str) -> list:
    return LOGS_APP.get(servicio, [])


@tool(
    description="Devuelve métricas actuales y valores normales de un servicio.",
    parameters={"servicio": {"description": "Nombre del servicio.", "type": "string"}},
)
def consultar_metricas_servicio(servicio: str) -> dict:
    return METRICAS_SERVICIO.get(servicio, {"error": "servicio no encontrado"})


# ────────────────────────────────────────────────────────────────────
# Tools compartidas por ambos agentes
# ────────────────────────────────────────────────────────────────────
# `compartir_hallazgo` cierra el turno del agente. Una regla del Monitor
# del loop (más abajo) detecta esta llamada y appendea una entry
# `hallazgo` al History — esa es la entrega estructurada para el otro.
@tool(
    description=(
        "Comparte un hallazgo con el otro agente. Llámala cuando hayas "
        "obtenido conclusiones de tu investigación en este turno."
    ),
    parameters={
        "observacion": {
            "description": "Hecho concreto observado en tus tools.",
            "type": "string",
        },
        "hipotesis": {
            "description": "Tu hipótesis sobre la causa basada en esa observación.",
            "type": "string",
        },
    },
)
def compartir_hallazgo(observacion: str, hipotesis: str) -> dict:
    return {"observacion": observacion, "hipotesis": hipotesis}


@tool(
    description=(
        "Cierra el diagnóstico con la causa raíz consensuada entre ambos "
        "dominios. Llámala SOLO si los hallazgos compartidos por ambos "
        "agentes apuntan claramente a la misma causa. Si solo tienes "
        "información de tu lado, comparte hallazgo y deja que el otro "
        "agente investigue antes de cerrar."
    ),
    parameters={
        "causa_raiz": {
            "description": "Síntesis de la causa raíz que une ambos dominios.",
            "type": "string",
        },
        "accion_recomendada": {
            "description": "Acción concreta a tomar.",
            "type": "string",
        },
    },
)
def cerrar_diagnostico(causa_raiz: str, accion_recomendada: str) -> dict:
    return {"causa_raiz": causa_raiz, "accion_recomendada": accion_recomendada}


PROVIDER = "openai"
MODEL = "gpt-4.1-mini"
API_KEY = os.environ.get("OPEN_AI_API_KEY")

if not API_KEY:
    print("ERROR: falta OPEN_AI_API_KEY en el entorno.")
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────
# Acción del Monitor: publicar `hallazgo` cuando se llama `compartir_hallazgo`
# ────────────────────────────────────────────────────────────────────
# Cada agente tiene una versión propia de esta acción que appendea con
# su `dominio` para que las vistas puedan filtrar/etiquetar.
def crear_publicador_hallazgo(dominio: str):
    def publicar(history: History) -> None:
        ultima_tc = next(
            (e for e in reversed(history.all()) if e.type == "tool_call"),
            None,
        )
        if not ultima_tc:
            return
        if ultima_tc.content.get("name") != "compartir_hallazgo":
            return
        args = ultima_tc.content.get("arguments") or {}
        history.append(
            author=f"agente_{dominio}",
            type="hallazgo",
            content={
                "dominio": dominio,
                "observacion": args.get("observacion", ""),
                "hipotesis": args.get("hipotesis", ""),
            },
        )
    return publicar


# ────────────────────────────────────────────────────────────────────
# Vista por dominio — cada agente ve hallazgos cruzados, no pasos internos
# ────────────────────────────────────────────────────────────────────
# Tres bloques (mismo esquema que el ejemplo 06, ahora con sinergia):
#   1. Hallazgos compartidos en la investigación (de AMBOS dominios,
#      etiquetados como "tu hallazgo" o "hallazgo de Infra/App").
#   2. Mensaje actual del usuario / orquestador para esta ronda.
#   3. Lo que TÚ ya hiciste en este turno (tool_calls del run actual,
#      excluyendo las tools de coordinación).
#
# Los `tool_call` intermedios del OTRO agente (sus consultas detalladas)
# nunca cruzan: el otro lado solo te entrega su síntesis (`hallazgo`).
def crear_vista_dominio(mi_dominio: str):
    NOMBRES_DOMINIO = {"infra": "Infra", "app": "App"}

    def vista(history: History) -> str:
        rid_actual = current_run_id(history)

        # 1. Hallazgos de ambos dominios (cualquier run, ordenados por id).
        hallazgos = sorted(history.by_type("hallazgo"), key=lambda e: e.id)

        # 2. Mensaje del run actual.
        prompts_actuales = [
            e for e in history.by_type("prompt")
            if isinstance(e.content, dict) and e.content.get("run_id") == rid_actual
        ]
        mensaje_actual = (
            prompts_actuales[0].content.get("text", "")
            if prompts_actuales else ""
        )

        # 3. Trabajo del agente en este turno (tool_calls del run actual,
        #    excluyendo las dos tools de coordinación porque ya están
        #    representadas en otros bloques).
        trabajo = []
        for tc in history.by_type("tool_call"):
            c = tc.content if isinstance(tc.content, dict) else {}
            if c.get("run_id") != rid_actual:
                continue
            if c.get("name") in ("compartir_hallazgo", "cerrar_diagnostico"):
                continue
            trabajo.append(tc)
        trabajo.sort(key=lambda e: e.id)

        lines: list[str] = []
        if hallazgos:
            lines.append("Hallazgos compartidos hasta ahora:")
            for h in hallazgos:
                hc = h.content if isinstance(h.content, dict) else {}
                d = hc.get("dominio", "?")
                obs = hc.get("observacion", "")
                hip = hc.get("hipotesis", "")
                etiqueta = (
                    "Tu hallazgo"
                    if d == mi_dominio
                    else f"Hallazgo de {NOMBRES_DOMINIO.get(d, d.title())}"
                )
                lines.append(f"  [{etiqueta}]")
                lines.append(f"    observación: {obs}")
                lines.append(f"    hipótesis:   {hip}")
            lines.append("")
        else:
            lines.append("(Todavía no hay hallazgos compartidos.)")
            lines.append("")

        lines.append(f"Instrucción para tu turno: {mensaje_actual}")

        if trabajo:
            lines.append("")
            lines.append("Tu trabajo en este turno hasta ahora:")
            for tc in trabajo:
                c = tc.content
                name = c.get("name")
                args = c.get("arguments") or {}
                result = c.get("result")
                rs = json.dumps(result, ensure_ascii=False, default=str)
                if len(rs) > 220:
                    rs = rs[:220] + "..."
                lines.append(f"  {name}({args}) → {rs}")

        return "\n".join(lines)

    return vista


# ────────────────────────────────────────────────────────────────────
# Construcción de los dos agentes y los dos loops
# ────────────────────────────────────────────────────────────────────
ROLE_INFRA = """\
Eres el especialista de Infraestructura. Diagnosticas alertas mirando
recursos físicos del servidor: memoria, swap, CPU, evolución temporal.

Tu colega es el especialista de Aplicación. En cada ronda recibes los
hallazgos que él compartió. Juntos llegan a la causa raíz.

Flujo de tu turno:
1. Consulta tus tools (`consultar_recursos_servidor`,
   `consultar_historico_memoria`) para investigar.
2. Si tu colega aún NO compartió hallazgos: llama `compartir_hallazgo`
   con tu observación e hipótesis. Se cerrará tu turno.
3. Si tu colega ya compartió y la causa raíz emerge de ambos dominios:
   llama `cerrar_diagnostico` con la síntesis y la acción a tomar.
4. NUNCA llames `cerrar_diagnostico` sin haber visto hallazgos de
   ambos dominios. Si solo viste el tuyo, comparte y espera.
"""

ROLE_APP = """\
Eres el especialista de Aplicación. Diagnosticas alertas mirando el
comportamiento del software: logs, métricas de servicios, conexiones.

Tu colega es el especialista de Infraestructura. En cada ronda recibes
los hallazgos que él compartió. Juntos llegan a la causa raíz.

Flujo de tu turno:
1. Consulta tus tools (`consultar_logs_aplicacion`,
   `consultar_metricas_servicio`) para investigar.
2. Si tu colega aún NO compartió hallazgos: llama `compartir_hallazgo`
   con tu observación e hipótesis. Se cerrará tu turno.
3. Si tu colega ya compartió y la causa raíz emerge de ambos dominios:
   llama `cerrar_diagnostico` con la síntesis y la acción a tomar.
4. NUNCA llames `cerrar_diagnostico` sin haber visto hallazgos de
   ambos dominios. Si solo viste el tuyo, comparte y espera.
"""


def construir_setup(history: History):
    """Construye los dos agentes y los dos loops, conectados al mismo
    History con vistas separadas y monitors propios."""

    # Vistas: ambas registradas en el mismo History con nombres distintos.
    history.add_view("vista_infra", crear_vista_dominio("infra"))
    history.add_view("vista_app", crear_vista_dominio("app"))

    # Monitor de Infra: publica `hallazgo` con dominio="infra".
    monitor_infra = Monitor(name="monitor_infra")
    monitor_infra.add_rule(
        when_last_tool_called("compartir_hallazgo"),
        crear_publicador_hallazgo("infra"),
    )

    # Monitor de App: idéntico pero con dominio="app".
    monitor_app = Monitor(name="monitor_app")
    monitor_app.add_rule(
        when_last_tool_called("compartir_hallazgo"),
        crear_publicador_hallazgo("app"),
    )

    # Agente Infra. Seteamos `agent.name` como atributo (no hay kwarg
    # `name` en el constructor) para que el bridge lo use como `author`
    # de las entries — así distinguimos en el History quién hizo qué.
    agente_infra = InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup=ROLE_INFRA,
        tools=[
            consultar_recursos_servidor,
            consultar_historico_memoria,
            compartir_hallazgo,
            cerrar_diagnostico,
        ],
    )
    agente_infra.name = "agente_infra"
    loop_infra = InstantLoop(
        agent=agente_infra,
        history=history,
        name="loop_infra",
        view="vista_infra",
        monitors=monitor_infra,
        stop_tool=["compartir_hallazgo", "cerrar_diagnostico"],
        max_steps=6,
    )

    # Agente App. Construcción simétrica.
    agente_app = InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup=ROLE_APP,
        tools=[
            consultar_logs_aplicacion,
            consultar_metricas_servicio,
            compartir_hallazgo,
            cerrar_diagnostico,
        ],
    )
    agente_app.name = "agente_app"
    loop_app = InstantLoop(
        agent=agente_app,
        history=history,
        name="loop_app",
        view="vista_app",
        monitors=monitor_app,
        stop_tool=["compartir_hallazgo", "cerrar_diagnostico"],
        max_steps=6,
    )

    return loop_infra, loop_app


# ────────────────────────────────────────────────────────────────────
# Coreografía: alternar los dos loops hasta que alguno cierre el diagnóstico
# ────────────────────────────────────────────────────────────────────
ALERTA_INICIAL = (
    "Alerta crítica: memoria al 95% en el servidor 'prod-app-01' que aloja "
    "el servicio 'pagos-api'. Investiga desde tu dominio y coordina con el "
    "otro especialista."
)


def section(title: str) -> None:
    print()
    print("─" * 64)
    print(title)
    print("─" * 64)


def main() -> None:
    history = History(name="incidente_compartido")
    loop_infra, loop_app = construir_setup(history)

    section("ALERTA")
    print(f"  {ALERTA_INICIAL}")

    # Bucle exterior: alternamos infra → app → infra → app hasta que
    # alguno llame cerrar_diagnostico. Cap de 3 rondas (= 6 runs).
    secuencia = [(loop_infra, "INFRA"), (loop_app, "APP")]
    cerrado = False
    runs_totales = 0

    for ronda in range(1, 4):
        for loop_actual, etiqueta in secuencia:
            section(f"RONDA {ronda} — turno de {etiqueta}")
            r = loop_actual.run(ALERTA_INICIAL)
            runs_totales += 1
            print(
                f"  resultado: {r.terminated_reason} "
                f"({r.total_steps} steps, stop_reason={r.stop_reason!r})"
            )

            if r.stop_reason and "cerrar_diagnostico" in r.stop_reason:
                cerrado = True
                break
        if cerrado:
            break

    # ────────────────────────────────────────────────────────────────
    # Resultados
    # ────────────────────────────────────────────────────────────────
    section("HALLAZGOS EN EL HISTORY")
    for h in history.by_type("hallazgo"):
        c = h.content
        print(f"  [{c['dominio'].upper()}]")
        print(f"    obs: {c['observacion']}")
        print(f"    hip: {c['hipotesis']}")

    section("DIAGNÓSTICO FINAL")
    cierre = next(
        (tc for tc in history.by_type("tool_call")
         if tc.content.get("name") == "cerrar_diagnostico"),
        None,
    )
    if cierre:
        args = cierre.content.get("arguments") or {}
        print(f"  causa raíz       : {args.get('causa_raiz')}")
        print(f"  acción           : {args.get('accion_recomendada')}")
        print(f"  cerrado por      : {cierre.content.get('origin')}")
    else:
        print("  No se llegó a consenso en 3 rondas.")

    section("RESUMEN")
    print(f"  runs totales       : {runs_totales}")
    print(f"  hallazgos en log   : {len(history.by_type('hallazgo'))}")
    print(f"  entries en History : {len(history.all())}")
    print(f"  cerrado            : {cerrado}")

    # ────────────────────────────────────────────────────────────────
    # Verificaciones mínimas
    # ────────────────────────────────────────────────────────────────
    # Cada agente debería haber producido al menos un hallazgo.
    dominios_con_hallazgo = {
        h.content["dominio"] for h in history.by_type("hallazgo")
    }
    assert "infra" in dominios_con_hallazgo
    assert "app" in dominios_con_hallazgo
    assert cerrado, "se esperaba consenso en 3 rondas"

    print("\n✅ Ejemplo 07 completado correctamente.")


if __name__ == "__main__":
    main()
