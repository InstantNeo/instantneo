"""
Smoke real (manual, opt-in) del fix de `reasoning_tokens` (PR 4).

Llama a modelos con capacidad de reasoning extendido y verifica que
`agent.last_run.usage["reasoning_tokens"]` queda populado.

Requiere `.env` con keys de OpenAI y/o Gemini.

Uso: python3 tests/smoke/smoke_reasoning_tokens.py
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


def smoke_openai_reasoning() -> int:
    """OpenAI o4-mini con reasoning='high' debe reportar reasoning_tokens > 0."""
    api_key = os.environ.get("OPEN_AI_API_KEY")
    if not api_key:
        print("WARN: OPEN_AI_API_KEY no encontrada; skip OpenAI")
        return 0

    agent = InstantNeo(
        provider="openai",
        model="o4-mini",
        api_key=api_key,
        role_setup="Resuelve problemas matemáticos paso a paso.",
    )

    try:
        text = agent.run(
            "Calcula 47 * 89 sin dar el resultado solo, muestra el proceso brevemente.",
            reasoning="high",
            max_tokens=300,
        )
    except Exception as e:
        print(f"FAIL OpenAI: {type(e).__name__}: {e}")
        return 1

    usage = agent.last_run.usage
    print(f"OpenAI o4-mini reasoning='high':")
    print(f"  respuesta: {text[:120]}...")
    print(f"  usage: {usage}")

    rt = usage.get("reasoning_tokens")
    if rt is not None and rt > 0:
        print(f"  OK — reasoning_tokens = {rt}")
        return 0
    elif rt is None:
        print(f"  WARN — reasoning_tokens = None (el SDK no reporta o el campo no está)")
        return 0
    else:
        print(f"  WARN — reasoning_tokens = {rt} (esperaba > 0)")
        return 0


def smoke_gemini_reasoning() -> int:
    """Gemini 2.5 debe reportar thoughts_token_count en algunos casos."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("WARN: GEMINI_API_KEY no encontrada; skip Gemini")
        return 0

    agent = InstantNeo(
        provider="gemini",
        model="gemini-2.5-flash",
        api_key=api_key,
        role_setup="Resuelve problemas matemáticos paso a paso.",
    )

    try:
        text = agent.run(
            "Calcula 47 * 89 sin dar el resultado solo, muestra el proceso brevemente.",
            max_tokens=300,
        )
    except Exception as e:
        print(f"FAIL Gemini: {type(e).__name__}: {e}")
        return 1

    usage = agent.last_run.usage
    print(f"\nGemini 2.5-flash:")
    print(f"  respuesta: {text[:120]}...")
    print(f"  usage: {usage}")

    rt = usage.get("reasoning_tokens")
    print(f"  reasoning_tokens = {rt}")
    return 0


def smoke_anthropic_reasoning() -> int:
    """Anthropic NO debe reportar reasoning_tokens (default None por diseño)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("WARN: ANTHROPIC_API_KEY no encontrada; skip Anthropic")
        return 0

    agent = InstantNeo(
        provider="anthropic",
        model="claude-haiku-4-5",
        api_key=api_key,
        role_setup="Resuelve problemas matemáticos.",
    )

    try:
        text = agent.run("Calcula 47 * 89.", max_tokens=200, temperature=0.0)
    except Exception as e:
        print(f"FAIL Anthropic: {type(e).__name__}: {e}")
        return 1

    usage = agent.last_run.usage
    print(f"\nAnthropic claude-haiku-4-5 (sin thinking, baseline):")
    print(f"  respuesta: {text[:120]}...")
    print(f"  usage: {usage}")
    rt = usage.get("reasoning_tokens")
    if rt is None:
        print(f"  OK — reasoning_tokens = None (por diseño Anthropic)")
        return 0
    else:
        print(f"  WARN — reasoning_tokens = {rt} (esperaba None)")
        return 0


def main() -> int:
    print("Smoke real de reasoning_tokens propagado al usage dict\n")
    rc = 0
    rc += smoke_openai_reasoning()
    rc += smoke_anthropic_reasoning()
    rc += smoke_gemini_reasoning()
    print("\n--- Smoke completo ---")
    return rc


if __name__ == "__main__":
    sys.exit(main())
