"""
Smoke real (opt-in) de propagación de ``reasoning_tokens`` (PR 4)
cross-provider.

Itera sobre providers reasoning-capable disponibles en `.env` y
verifica que ``agent.last_run.usage["reasoning_tokens"]`` queda
populado correctamente según el comportamiento esperado de cada
provider:

- OpenAI o4-mini con reasoning='high' → debería reportar > 0.
- Anthropic claude (sin extended thinking) → None por diseño
  (Anthropic mete thinking tokens dentro de output_tokens).
- Gemini 2.5+ → reporta thoughts_token_count cuando aplica.
- Groq qwen-3 reasoning → puede reportar.
- xAI grok-3-fast → puede reportar.

Lo importante es que el CAMPO ``reasoning_tokens`` está presente en
``usage`` (no falta como key) en TODOS los providers, con valor int
o None según corresponda.

Requiere `.env`.

Uso: `python3 tests/smoke/smoke_reasoning_tokens.py`
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
# Matriz: (provider, model, env_var, run_kwargs, expectation)
#
# `expectation` puede ser:
#   "non_zero" → reasoning_tokens debe ser int > 0
#   "none_by_design" → debe ser None (Anthropic)
#   "any_int_or_none" → cualquier int o None es OK (modelo puede o no usar)
# ────────────────────────────────────────────────────────────────────

PROVIDERS = [
    ("openai",    "o4-mini",                  "OPEN_AI_API_KEY",
     {"reasoning": "high"}, "non_zero"),
    ("anthropic", "claude-haiku-4-5",         "ANTHROPIC_API_KEY",
     {}, "none_by_design"),
    ("gemini",    "gemini-2.5-flash",         "GEMINI_API_KEY",
     {}, "any_int_or_none"),
    ("xai",       "grok-3-fast",              "XAI_API_KEY",
     {}, "any_int_or_none"),
]


PROMPT = "Calculá 47 × 89 paso a paso (mostrá el proceso brevemente)."


# Tokens en errores de API que indican issue de cuenta/billing.
_BILLING_ERROR_TOKENS = ("credit balance", "billing", "quota exceeded",
                          "insufficient_quota", "payment", "account_inactive")


def _is_billing_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(tok in msg for tok in _BILLING_ERROR_TOKENS)


# ────────────────────────────────────────────────────────────────────
# Caso único: agent.run y verificar usage["reasoning_tokens"]
# ────────────────────────────────────────────────────────────────────

def case_reasoning_tokens_propagated(
    provider: str, model: str, api_key: str,
    extra_kwargs: dict, expectation: str,
) -> bool:
    agent = InstantNeo(
        provider=provider, model=model, api_key=api_key,
        role_setup="Resolvé problemas matemáticos paso a paso.",
    )
    try:
        # Sin temperature — algunos reasoning models (e.g. o4-mini) no la
        # soportan. extra_kwargs puede traer reasoning="high" para OpenAI.
        agent.run(PROMPT, max_tokens=400, **extra_kwargs)
    except Exception as e:
        if _is_billing_error(e):
            raise
        print(f"      LLM call failed: {type(e).__name__}: {e}")
        return False

    usage = agent.last_run.usage
    rt = usage.get("reasoning_tokens")
    print(f"      usage: {usage}")

    # Verificación según expectation
    if expectation == "non_zero":
        if isinstance(rt, int) and rt > 0:
            print(f"      OK — reasoning_tokens={rt} (esperado > 0)")
            return True
        print(f"      FAIL — esperaba reasoning_tokens > 0, got {rt!r}")
        return False
    elif expectation == "none_by_design":
        if rt is None:
            print(f"      OK — reasoning_tokens=None (por diseño Anthropic)")
            return True
        print(f"      FAIL — esperaba None por diseño, got {rt!r}")
        return False
    elif expectation == "any_int_or_none":
        if rt is None or isinstance(rt, int):
            print(f"      OK — reasoning_tokens={rt} (cualquier int o None)")
            return True
        print(f"      FAIL — tipo inesperado: {rt!r}")
        return False
    else:
        raise ValueError(f"expectation desconocida: {expectation}")


def case_reasoning_tokens_key_always_present(
    provider: str, model: str, api_key: str,
    extra_kwargs: dict, expectation: str,
) -> bool:
    """Sub-caso garantía: la KEY 'reasoning_tokens' siempre está en usage,
    incluso si el valor es None. Esto es contrato post-PR 4."""
    agent = InstantNeo(
        provider=provider, model=model, api_key=api_key,
        role_setup="Sos conciso.",
    )
    try:
        # No usamos temperature porque algunos reasoning models (o4-mini)
        # no la soportan; max_tokens generoso para que no trunque.
        agent.run("Decí 'ok'.", max_tokens=200)
    except Exception as e:
        if _is_billing_error(e):
            raise
        print(f"      [key-check] LLM call failed: {type(e).__name__}: {e}")
        return False

    usage = agent.last_run.usage
    if "reasoning_tokens" in usage:
        print(f"      [key-check] OK — key 'reasoning_tokens' presente (value={usage['reasoning_tokens']!r})")
        return True
    print(f"      [key-check] FAIL — key 'reasoning_tokens' AUSENTE en usage={usage}")
    return False


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("Smoke real de reasoning_tokens cross-provider")
    print("=" * 60)

    total_run, total_pass, total_skip = 0, 0, 0
    results = []

    for provider, model, env_var, extra_kwargs, expectation in PROVIDERS:
        api_key = os.environ.get(env_var)
        print(f"\n[{provider} | {model}] (expect: {expectation})")
        if not api_key:
            print(f"      SKIP — {env_var} no encontrada en .env")
            total_skip += 1
            results.append((provider, "SKIP"))
            continue

        cases_ok = 0
        billing_skip = False
        # Caso 1: valor según expectation
        total_run += 1
        try:
            if case_reasoning_tokens_propagated(provider, model, api_key,
                                                  extra_kwargs, expectation):
                cases_ok += 1
                total_pass += 1
        except Exception as e:
            if _is_billing_error(e):
                print(f"      BILLING SKIP: {str(e)[:80]}")
                billing_skip = True
                total_run -= 1
            else:
                print(f"      EXCEPTION: {type(e).__name__}: {e}")

        # Caso 2: key siempre presente (contrato del fix)
        total_run += 1
        try:
            if case_reasoning_tokens_key_always_present(provider, model, api_key,
                                                          extra_kwargs, expectation):
                cases_ok += 1
                total_pass += 1
        except Exception as e:
            if _is_billing_error(e):
                print(f"      [key-check] BILLING SKIP: {str(e)[:80]}")
                billing_skip = True
                total_run -= 1
            else:
                print(f"      [key-check] EXCEPTION: {type(e).__name__}: {e}")

        if billing_skip and cases_ok == 0:
            results.append((provider, "BILLING_SKIP"))
        else:
            results.append((provider, f"{cases_ok}/2"))

    print("\n" + "=" * 60)
    print("Resumen (cada provider: 1 caso de valor + 1 de presencia de key):")
    for provider, status in results:
        print(f"  {provider:12s} {status}")
    print(f"\nTotal: {total_pass}/{total_run} casos OK, {total_skip} providers skipped")
    return 0 if total_pass == total_run else 1


if __name__ == "__main__":
    sys.exit(main())
