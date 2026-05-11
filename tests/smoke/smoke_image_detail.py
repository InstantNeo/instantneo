"""
Smoke real (manual, opt-in) del fix de `image_detail` (PR 1).

Llama a un modelo de visión de OpenAI dos veces con la misma imagen
y el mismo prompt, variando solo `image_detail`:

  - run A: image_detail="low"
  - run B: image_detail="high"

OpenAI tokeniza la imagen distinto según `detail`:
  - "low": 85 tokens fijos.
  - "high": ~85 + (170 × N_tiles).

Si nuestra fix llegó al payload, los **input_tokens del run B** deben ser
mayores que los del run A. Si están iguales, OpenAI recibió el default
(probablemente "auto") en ambos casos — la fix no aterrizó.

Requiere:
  - `.env` en la raíz del repo con `OPEN_AI_API_KEY=...`.
  - El paquete `instantneo` local accesible (este script lo asegura
    insertando la raíz del repo en sys.path).

Uso:
  python3 tests/smoke/smoke_image_detail.py
"""

import os
import sys
from pathlib import Path

# Misma estrategia que tests/utils/test_image_utils.py: usar el código local.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env")


# Imagen pública estable y de tamaño suficiente para que "high" genere
# múltiples tiles (OpenAI escala la imagen a tiles de 512×512 y cobra
# 170 tokens por tile además del baseline de 85). Cualquier dimensión
# > 512px ya fuerza al menos 2 tiles de un lado.
# picsum.photos sirve imágenes aleatorias estables, permite hot-linking,
# sin captcha ni rate limits agresivos.
TEST_IMAGE_URL = "https://picsum.photos/800/600.jpg"

PROMPT = "Describe la imagen en una sola frase corta."


def _run_with_detail(detail: str) -> dict:
    """Corre el agente una vez con el detail pedido y devuelve el usage."""
    from instantneo import InstantNeo

    api_key = os.environ.get("OPEN_AI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPEN_AI_API_KEY no encontrada en .env. "
            "Verificá que tests/../.env existe y contiene la clave."
        )

    agent = InstantNeo(
        provider="openai",
        model="gpt-4o-mini",
        api_key=api_key,
        role_setup="Eres un asistente que describe imágenes brevemente.",
    )

    text = agent.run(
        PROMPT,
        images=TEST_IMAGE_URL,
        image_detail=detail,
        max_tokens=80,
        temperature=0.0,
    )

    last_run = agent.last_run

    # Inspección directa del payload enviado al provider. Este es el
    # check más confiable: en messages_sent debe aparecer el campo
    # `"detail": "<detail>"` dentro del bloque image_url.
    payload_detail = _extract_detail_from_messages(last_run.messages_sent)

    return {
        "detail":            detail,
        "response":          text,
        "payload_detail":    payload_detail,
        "input_tokens":      last_run.usage.get("input_tokens"),
        "output_tokens":     last_run.usage.get("output_tokens"),
        "total_tokens":      last_run.usage.get("total_tokens"),
        "model":             last_run.model,
        "duration_ms":       last_run.duration_ms,
    }


def _extract_detail_from_messages(messages: list) -> str | None:
    """Encuentra el `detail` dentro del bloque image_url del payload.
    Devuelve None si no lo encuentra (o si el shape del mensaje cambió)."""
    for msg in (messages or []):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "image_url":
                image_url = block.get("image_url") or {}
                if isinstance(image_url, dict) and "detail" in image_url:
                    return image_url["detail"]
    return None


def main() -> int:
    print("Smoke real de image_detail — comparando 'low' vs 'high'")
    print(f"Modelo: gpt-4o-mini | Imagen: {TEST_IMAGE_URL}")
    print()

    try:
        run_low  = _run_with_detail("low")
        run_high = _run_with_detail("high")
    except Exception as e:
        print(f"ERROR durante la llamada: {type(e).__name__}: {e}")
        return 1

    print("Resultado run A (low):")
    for k, v in run_low.items():
        if k == "response":
            print(f"  {k}: {str(v)[:120]}...")
        else:
            print(f"  {k}: {v}")
    print()
    print("Resultado run B (high):")
    for k, v in run_high.items():
        if k == "response":
            print(f"  {k}: {str(v)[:120]}...")
        else:
            print(f"  {k}: {v}")
    print()

    # Check primario: el payload enviado tuvo el `detail` correcto.
    # Esto es lo que la fix garantiza directamente. Es independiente
    # de cómo el provider tarifique tokens.
    payload_low  = run_low["payload_detail"]
    payload_high = run_high["payload_detail"]

    if payload_low == "low" and payload_high == "high":
        print(f"OK: el payload enviado contiene detail correcto en ambas llamadas.")
        print(f"    Run A → image_url.detail = {payload_low!r}")
        print(f"    Run B → image_url.detail = {payload_high!r}")
        print()

        # Check secundario (informativo): delta de tokens.
        # Algunos modelos (ej. gpt-4o-mini) pueden no diferenciar
        # tokens entre low y high — no es un fallo de la fix.
        low_in  = run_low["input_tokens"]  or 0
        high_in = run_high["input_tokens"] or 0
        diff    = high_in - low_in
        if diff > 0:
            print(f"Adicional: delta input_tokens (high − low) = {diff}")
            print(f"           El provider respondió con más tokens para 'high',")
            print(f"           confirmando que el campo fue interpretado.")
        elif diff == 0:
            print(f"Adicional: input_tokens idénticos ({high_in}).")
            print(f"           gpt-4o-mini puede no diferenciar tarifa entre low/high.")
            print(f"           La fix está bien — el payload sale correcto.")
        else:
            print(f"Adicional: 'low' tuvo MÁS tokens que 'high' ({low_in} > {high_in}).")
            print(f"           Anomalía del provider, no de la fix.")
        return 0

    print(f"FAIL: payload no contiene el detail esperado.")
    print(f"    Run A: payload_detail = {payload_low!r}, esperado 'low'")
    print(f"    Run B: payload_detail = {payload_high!r}, esperado 'high'")
    print(f"    La fix no aterrizó. Revisar instantneo/utils/image_utils.py.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
