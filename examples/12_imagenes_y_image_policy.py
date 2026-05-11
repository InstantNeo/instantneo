"""
Ejemplo 12 — Imágenes en el Loop: `image_policy`
==================================================

Caso funcional
--------------
El usuario adjunta una imagen al prompt y el agente trabaja varios
turnos sobre ella. La vista `loop_default` decide **en qué steps se
le envía la imagen al provider** mediante el parámetro `image_policy`.

Tres modos:

  - ``"every_turn"`` (default): la imagen va en cada step. El agente
    siempre la puede consultar.
  - ``"first_only"``: solo en el step 1. En los steps siguientes el
    agente trabaja con lo que él mismo describió de la imagen en su
    primer response. Útil cuando la imagen es el input inicial pero
    los pasos siguientes son acciones sobre la conclusión.
  - ``"none"``: nunca se le manda al provider. El history puede
    mencionarla como referencia (auditoría) pero el agente no la
    ve. Útil cuando guardás la imagen en el log por compliance pero
    no querés que el agente la procese.

Qué muestra este ejemplo
------------------------
1. El usuario adjunta una imagen via `loop.run(prompt, images=[path])`.
2. Corremos el mismo prompt con las dos políticas relevantes
   (`every_turn` y `first_only`).
3. Para cada run, inspeccionamos los `messages_sent` de cada step del
   `RunLog` y mostramos EXACTAMENTE en qué steps la imagen llegó al
   provider. Esa es la métrica funcional concreta del `image_policy`.

Cómo correr
-----------
    python3 examples/12_imagenes_y_image_policy.py

Nota: este ejemplo usa una imagen local del repo (`docs/img/logo_instantneo.png`).
No requiere conexión a internet adicional más allá del provider del LLM.
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

from instantneo import History, InstantLoop, InstantNeo, tool
from instantneo.loop.default_view import loop_default


# ────────────────────────────────────────────────────────────────────
# Catálogo simulado y tools del agente
# ────────────────────────────────────────────────────────────────────
# Imagen usada: el logo de InstantNeo (texto/diseño con letras). El
# catálogo está armado con items que matchean con "logo", "texto",
# "marca", "tipografía" — términos que un agente describiendo un
# logo va a usar.
CATALOGO = [
    {"id": "P-001", "nombre": "Sticker de logo personalizado",  "tags": ["logo", "sticker", "marca"], "stock": 24},
    {"id": "P-002", "nombre": "Plantilla de identidad visual",  "tags": ["logo", "tipografia", "marca"], "stock": 8},
    {"id": "P-003", "nombre": "Tarjeta de presentación",         "tags": ["tarjeta", "marca", "texto"], "stock": 30},
    {"id": "P-004", "nombre": "Tipografía decorativa premium",   "tags": ["tipografia", "texto", "diseño"], "stock": 15},
]


@tool(
    description=(
        "Busca en el catálogo productos cuyo nombre o tags coincidan con "
        "el término. Devuelve hasta 5 items."
    ),
    parameters={"termino": {"description": "Término de búsqueda.", "type": "string"}},
)
def consultar_catalogo(termino: str) -> list:
    t = termino.lower()
    return [
        p for p in CATALOGO
        if t in p["nombre"].lower() or any(t in tag for tag in p["tags"])
    ][:5]


@tool(
    description="Entrega la respuesta final al usuario.",
    parameters={"mensaje": {"description": "Respuesta.", "type": "string"}},
)
def responder(mensaje: str) -> dict:
    return {"mensaje": mensaje}


PROVIDER = "openai"
MODEL = "gpt-4.1-mini"
API_KEY = os.environ.get("OPEN_AI_API_KEY")

if not API_KEY:
    print("ERROR: falta OPEN_AI_API_KEY en el entorno.")
    sys.exit(1)


# Imagen local del repo. Es un PNG del logo de InstantNeo. Path
# resuelto desde la raíz del worktree.
IMAGEN_PATH = str(_REPO_ROOT / "docs" / "img" / "logo_instantneo.png")
if not Path(IMAGEN_PATH).exists():
    print(f"ERROR: no encontré la imagen en {IMAGEN_PATH}")
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────
# Factory de vistas con `image_policy` configurable
# ────────────────────────────────────────────────────────────────────
# `loop_default` acepta `image_policy` como kwarg. La función que
# registramos en el History no acepta args (la vista recibe solo el
# History), así que envolvemos en un closure que fija la policy.
def crear_vista_con_policy(policy: str):
    def vista(history):
        return loop_default(history, image_policy=policy)
    return vista


# Activamos debug=True para tener un RunLog con un TurnLog por step.
# El TurnLog incluye `messages_sent`, la lista literal de mensajes
# enviados al provider en ese step. Ahí vemos si la imagen viajó o no.
DEBUG_DIR = Path("/tmp/instantneo_ejemplo12_debug")


def imagen_presente_en_messages(messages_sent: list) -> bool:
    """Determina si los `messages_sent` de un step incluyen una imagen.

    El shape OpenAI/Chat Completions: messages con `content` como lista
    de bloques `{"type": "image_url", "image_url": {...}}`. Verificamos
    si algún bloque es de tipo image_url.
    """
    for msg in messages_sent or []:
        content = msg.get("content")
        if isinstance(content, list):
            for bloque in content:
                if isinstance(bloque, dict) and bloque.get("type") == "image_url":
                    return True
    return False


def correr_experimento(view_name: str, image_policy: str) -> tuple[History, object]:
    """Construye agente + loop con la vista pedida y corre la misma
    tarea con la misma imagen. Devuelve History + RunResult."""
    history = History(name=f"img_demo_{image_policy}")
    history.add_view(view_name, crear_vista_con_policy(image_policy))

    agente = InstantNeo(
        provider=PROVIDER, model=MODEL, api_key=API_KEY,
        role_setup=(
            "Eres un asistente que ayuda a buscar productos en el "
            "catálogo. Sé MUY CONCISO en tu texto (una sola oración "
            "para describir la imagen). Flujo:\n"
            "1. Describe la imagen en una oración.\n"
            "2. Llama `consultar_catalogo` con el primer término.\n"
            "3. Llama `consultar_catalogo` con el segundo término.\n"
            "4. Llama `consultar_catalogo` con el tercer término.\n"
            "5. Llama `responder` con los matches relevantes."
        ),
        tools=[consultar_catalogo, responder],
    )
    loop = InstantLoop(
        agent=agente,
        history=history,
        name=f"loop_{image_policy}",
        view=view_name,
        stop_tool="responder",
        max_steps=6,
        debug=True,
        debug_base_path=DEBUG_DIR,
    )
    result = loop.run(
        "Mira la imagen. Busca en el catálogo usando estos tres términos "
        "exactos en este orden: 'logo', 'marca', 'tipografia'. Luego "
        "reporta los matches relevantes.",
        images=[IMAGEN_PATH],
        image_detail="high",   # imagen pesa más → la diferencia se nota
    )
    return history, result


def detalle_imagen_por_step(result) -> list:
    """Para cada step del RunLog, devuelve (step_num, imagen_presente).
    Si `result.log` es None (no se activó debug), devuelve [].
    """
    if result.log is None:
        return []
    return [
        (t.step_num, imagen_presente_en_messages(t.messages_sent))
        for t in result.log.turns
    ]


def extraer_ultima_respuesta(history: History, run_id: str) -> str:
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


def main() -> None:
    print(f"Imagen usada: {IMAGEN_PATH}")
    # Limpieza del directorio de debug entre corridas.
    if DEBUG_DIR.exists():
        import shutil
        shutil.rmtree(DEBUG_DIR)

    # ────────────────────────────────────────────────────────────────
    # Run A — every_turn (imagen en cada step)
    # ────────────────────────────────────────────────────────────────
    section("RUN A — image_policy='every_turn'")
    print(">>> Ejecutando...")
    h_a, r_a = correr_experimento("vista_every", "every_turn")
    detalle_a = detalle_imagen_por_step(r_a)
    print(f"  resultado : {r_a.terminated_reason} ({r_a.total_steps} steps)")
    print(f"  imagen presente por step:")
    for step, presente in detalle_a:
        marca = "✓ imagen enviada" if presente else "✗ sin imagen"
        print(f"    step {step}: {marca}")

    # ────────────────────────────────────────────────────────────────
    # Run B — first_only (imagen solo en el step 1)
    # ────────────────────────────────────────────────────────────────
    section("RUN B — image_policy='first_only'")
    print(">>> Ejecutando...")
    h_b, r_b = correr_experimento("vista_first", "first_only")
    detalle_b = detalle_imagen_por_step(r_b)
    print(f"  resultado : {r_b.terminated_reason} ({r_b.total_steps} steps)")
    print(f"  imagen presente por step:")
    for step, presente in detalle_b:
        marca = "✓ imagen enviada" if presente else "✗ sin imagen"
        print(f"    step {step}: {marca}")

    # ────────────────────────────────────────────────────────────────
    # Contraste funcional
    # ────────────────────────────────────────────────────────────────
    section("CONTRASTE FUNCIONAL")
    print(f"  every_turn → imagen enviada en "
          f"{sum(1 for _, p in detalle_a if p)} de {len(detalle_a)} steps")
    print(f"  first_only → imagen enviada en "
          f"{sum(1 for _, p in detalle_b if p)} de {len(detalle_b)} steps")
    print()
    print("  En every_turn el agente puede consultar la imagen en cada step.")
    print("  En first_only el agente solo la ve en el step 1; en los siguientes")
    print("  trabaja con lo que ÉL MISMO describió en su primer response.")

    # ────────────────────────────────────────────────────────────────
    # Las respuestas finales deberían ser equivalentes en contenido
    # ────────────────────────────────────────────────────────────────
    section("RESPUESTAS FINALES")
    resp_a = extraer_ultima_respuesta(h_a, r_a.run_id)
    resp_b = extraer_ultima_respuesta(h_b, r_b.run_id)
    print("  Run A (every_turn):")
    print(f"    {resp_a[:300]}...")
    print()
    print("  Run B (first_only):")
    print(f"    {resp_b[:300]}...")

    # ────────────────────────────────────────────────────────────────
    # Verificaciones mínimas (funcionales)
    # ────────────────────────────────────────────────────────────────
    # 1. Ambos runs terminan correctamente.
    assert r_a.terminated_reason == "stop_signal"
    assert r_b.terminated_reason == "stop_signal"
    # 2. En every_turn la imagen está presente en TODOS los steps.
    assert all(presente for _, presente in detalle_a), (
        "every_turn debería enviar la imagen en cada step"
    )
    # 3. En first_only la imagen está SOLO en el step 1.
    assert detalle_b and detalle_b[0][1] is True, \
        "first_only debería enviar la imagen en el step 1"
    if len(detalle_b) > 1:
        assert all(not p for _, p in detalle_b[1:]), \
            "first_only no debería enviar la imagen en steps >1"

    print("\n✅ Ejemplo 12 completado correctamente.")


if __name__ == "__main__":
    main()
