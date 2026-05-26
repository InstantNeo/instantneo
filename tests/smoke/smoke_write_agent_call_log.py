"""
Smoke real (opt-in) de ``write_agent_call_log`` cross-provider (PR 7).

Para cada provider del .env: llama ``agent.run()`` real, persiste con
``write_agent_call_log``, carga con ``load_agent_call_logs``, verifica
shape end-to-end.

Requiere `.env`. Skippea providers sin key. Marca BILLING_SKIP si
una key existe pero la cuenta está sin créditos.

Uso: ``python3 tests/smoke/smoke_write_agent_call_log.py``
"""
import os
import sys
import tempfile
import json
from pathlib import Path
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
load_dotenv(_REPO_ROOT / ".env", override=True)

from instantneo import InstantNeo, AgentCapabilities, tool
from instantneo.debug import write_agent_call_log, load_agent_call_logs


PROVIDERS = [
    ("openai",    "gpt-5-mini",         "OPEN_AI_API_KEY"),
    ("anthropic", "claude-haiku-4-5",   "ANTHROPIC_API_KEY"),
    ("gemini",    "gemini-2.5-flash",   "GEMINI_API_KEY"),
    ("groq",      "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    ("xai",       "grok-3-fast",        "XAI_API_KEY"),
]


_BILLING_ERROR_TOKENS = ("credit balance", "billing", "quota exceeded",
                          "insufficient_quota", "payment", "account_inactive")


def _is_billing_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(tok in msg for tok in _BILLING_ERROR_TOKENS)


@tool(description="Get weather", parameters={
    "city": {"description": "City", "type": "str"},
})
def get_weather(city: str) -> dict:
    return {"city": city, "temp": 22}


def case_write_load_cycle(provider: str, model: str, api_key: str) -> bool:
    """Ciclo completo: agent.run() → write → load → verificar."""
    caps = AgentCapabilities(skills=[get_weather])

    agent = InstantNeo(
        provider=provider, model=model, api_key=api_key,
        role_setup="Sos un asistente conciso.",
        tools=caps,
    )

    try:
        agent.run("Decí 'listo' y nada más.", max_tokens=300)
    except Exception as e:
        if _is_billing_error(e):
            raise
        print(f"      LLM call failed: {type(e).__name__}: {e}")
        return False

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "smoke_calls"
        folder = base / f"{provider}_call"
        write_agent_call_log(agent, folder, call_id=f"smoke-{provider}",
                              extra={"smoke": True, "provider": provider})

        # Load
        loaded = load_agent_call_logs(base)
        if len(loaded) != 1:
            print(f"      FAIL — esperaba 1 loaded, got {len(loaded)}")
            return False

        cfg = loaded[0]["config"]
        call = loaded[0]["call"]

        # Verificaciones
        assert cfg["call_id"] == f"smoke-{provider}"
        assert cfg["extra"]["smoke"] is True
        assert cfg["agent"]["provider"] == provider
        assert cfg["agent"]["model"] == model
        assert len(cfg["agent"]["tools"]) == 1

        # No api_key leak
        config_text = json.dumps(cfg)
        assert api_key not in config_text, "API KEY LEAKED!"

        # TurnLog shape
        assert call["step_num"] == 1
        assert "usage" in call
        assert "run_params" in call
        assert call["provider"] == provider

        print(f"      OK — config+call escritos y cargados, "
              f"reasoning_tokens={call['usage'].get('reasoning_tokens')!r}, "
              f"prompt_len={len(call['prompt'])}")
        return True


def main() -> int:
    print("Smoke real de write_agent_call_log cross-provider")
    print("=" * 60)

    total_run, total_pass, total_skip = 0, 0, 0
    results = []

    for provider, model, env_var in PROVIDERS:
        api_key = os.environ.get(env_var)
        print(f"\n[{provider} | {model}]")
        if not api_key:
            print(f"      SKIP — {env_var} no encontrada")
            total_skip += 1
            results.append((provider, "SKIP"))
            continue

        total_run += 1
        try:
            if case_write_load_cycle(provider, model, api_key):
                total_pass += 1
                results.append((provider, "OK"))
            else:
                results.append((provider, "FAIL"))
        except Exception as e:
            if _is_billing_error(e):
                print(f"      BILLING SKIP: {str(e)[:80]}")
                total_run -= 1
                results.append((provider, "BILLING_SKIP"))
            else:
                print(f"      EXCEPTION: {type(e).__name__}: {e}")
                results.append((provider, "EXC"))

    print("\n" + "=" * 60)
    print("Resumen:")
    for provider, status in results:
        print(f"  {provider:12s} {status}")
    print(f"\nTotal: {total_pass}/{total_run} OK, {total_skip} skipped")
    return 0 if total_pass == total_run else 1


if __name__ == "__main__":
    sys.exit(main())
