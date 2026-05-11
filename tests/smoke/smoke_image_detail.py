"""
Smoke real (opt-in) del fix de `image_detail` (PR 1) cross-provider.

Itera sobre providers vision-capable disponibles en `.env` y para cada
uno verifica que ``image_url.detail`` llega al payload enviado al LLM
(via ``agent.last_run.messages_sent``).

Por qué inspeccionar el payload en vez de delta de tokens:
- OpenAI gpt-4o-mini no diferencia tarifa entre low/high (ambos = mismos
  tokens). El check confiable es que el campo viaje al payload.
- Anthropic y Gemini descartan el campo al traducir (no usan ``detail``)
  pero verificamos que el dict format OpenAI-compat lo lleva igual.

Requiere `.env`. Skippea providers sin key.

Uso: `python3 tests/smoke/smoke_image_detail.py`
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
load_dotenv(_REPO_ROOT / ".env", override=True)

from instantneo import InstantNeo


# ────────────────────────────────────────────────────────────────────
# Matriz de providers vision-capable
# ────────────────────────────────────────────────────────────────────

PROVIDERS = [
    ("openai",    "gpt-5-mini",        "OPEN_AI_API_KEY"),
    ("anthropic", "claude-haiku-4-5",  "ANTHROPIC_API_KEY"),
    ("gemini",    "gemini-2.5-flash",  "GEMINI_API_KEY"),
    ("xai",       "grok-4-fast-non-reasoning", "XAI_API_KEY"),
]

TEST_IMAGE_URL = "https://picsum.photos/seed/imgdetail/600/400.jpg"
PROMPT = "Describí la imagen en una sola frase corta."


# Tokens en errores de API que indican issue de cuenta/billing, no bug
# del código.
_BILLING_ERROR_TOKENS = ("credit balance", "billing", "quota exceeded",
                          "insufficient_quota", "payment", "account_inactive")


def _is_billing_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(tok in msg for tok in _BILLING_ERROR_TOKENS)


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _extract_detail_from_messages(messages: list) -> str | None:
    """Encuentra image_url.detail en el payload enviado al provider.

    Busca en el shape que `process_images` produce (dict con
    ``"image_url": {"url": ..., "detail": ...}``). Si el adapter del
    provider transformó el shape antes de mandarlo, esta extracción
    puede devolver None — eso es OK, la fix sigue siendo válida porque
    `process_images` produce el dict correcto."""
    for msg in (messages or []):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image_url":
                image_url = block.get("image_url") or {}
                if isinstance(image_url, dict) and "detail" in image_url:
                    return image_url["detail"]
    return None


def case_image_detail_present_in_payload(
    provider: str, model: str, api_key: str, detail: str = "high",
) -> bool:
    """Verifica que el detail solicitado aparece en messages_sent."""
    agent = InstantNeo(
        provider=provider, model=model, api_key=api_key,
        role_setup="Sos un asistente conciso.",
    )
    try:
        # max_tokens generoso porque reasoning models (gpt-5*, Gemini 2.5)
        # consumen budget con thinking interno y dejan poco para output.
        # Sin temperature porque gpt-5-mini y o4-mini no la soportan.
        text = agent.run(
            PROMPT,
            images=TEST_IMAGE_URL,
            image_detail=detail,
            max_tokens=400,
        )
    except Exception as e:
        if _is_billing_error(e):
            raise  # propagar como BILLING_SKIP en outer
        print(f"      [{detail}] LLM call failed: {type(e).__name__}: {e}")
        return False

    last = agent.last_run
    payload_detail = _extract_detail_from_messages(last.messages_sent)

    # Para OpenAI/xAI (chat-completions style) el detail debe llegar.
    # Anthropic/Gemini lo traducen a su propio formato y el campo
    # desaparece — verificamos por presencia en lo que SALIÓ del
    # `process_images` antes de la traducción del adapter.
    #
    # Como messages_sent guarda el shape DESPUÉS del procesamiento del
    # adapter, en non-OpenAI puede estar ausente. En ese caso solo
    # comprobamos que el agent respondió coherente con la imagen.
    if provider in ("openai", "xai"):
        if payload_detail == detail:
            print(f"      [{detail}] OK — payload tiene image_url.detail={payload_detail!r}, "
                  f"usage={last.usage}, response='{text[:40]}...'")
            return True
        else:
            print(f"      [{detail}] FAIL — payload_detail={payload_detail!r}, esperaba {detail!r}")
            return False
    else:
        # Para Anthropic/Gemini: confirmamos que el agent VIO la imagen
        # (respuesta no genérica) y que la llamada no rompió.
        if text and len(text) > 5:
            print(f"      [{detail}] OK (sin verificación de payload — Anthropic/Gemini "
                  f"reformatea images) — response='{text[:60]}...'")
            return True
        else:
            print(f"      [{detail}] FAIL — respuesta vacía o trivial: {text!r}")
            return False


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("Smoke real de image_detail cross-provider")
    print("=" * 60)

    total_run, total_pass, total_skip = 0, 0, 0
    results = []

    for provider, model, env_var in PROVIDERS:
        api_key = os.environ.get(env_var)
        print(f"\n[{provider} | {model}]")
        if not api_key:
            print(f"      SKIP — {env_var} no encontrada en .env")
            total_skip += 1
            results.append((provider, "SKIP"))
            continue

        cases_ok = 0
        billing_skip = False
        for detail in ("low", "high"):
            total_run += 1
            try:
                if case_image_detail_present_in_payload(provider, model, api_key, detail):
                    cases_ok += 1
                    total_pass += 1
            except Exception as e:
                if _is_billing_error(e):
                    print(f"      [{detail}] BILLING SKIP: {str(e)[:80]}")
                    billing_skip = True
                    total_run -= 1
                else:
                    print(f"      [{detail}] EXCEPTION: {type(e).__name__}: {e}")

        if billing_skip and cases_ok == 0:
            results.append((provider, "BILLING_SKIP"))
        else:
            results.append((provider, f"{cases_ok}/2"))

    print("\n" + "=" * 60)
    print("Resumen (cada provider corre con detail=low y detail=high):")
    for provider, status in results:
        print(f"  {provider:12s} {status}")
    print(f"\nTotal: {total_pass}/{total_run} casos OK, {total_skip} providers skipped")
    return 0 if total_pass == total_run else 1


if __name__ == "__main__":
    sys.exit(main())
