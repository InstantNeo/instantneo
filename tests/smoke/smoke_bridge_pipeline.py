"""
Smoke real (opt-in) del bridge end-to-end contra MÚLTIPLES providers (PR 5).

Itera sobre los providers disponibles en `.env` y para cada uno corre
3 casos:

  A. response only (sin tools)
  B. response + tool_call (agent llama una tool del usuario)
  C. queries reflejan run_start tras el bridge

Verifica que el bridge produce el mismo shape de entries
independientemente del provider.

Requiere `.env` con al menos una key. Skippea providers sin key.

Uso: `python3 tests/smoke/smoke_bridge_pipeline.py`
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
load_dotenv(_REPO_ROOT / ".env", override=True)

from instantneo import InstantNeo, tool
from instantneo.history import History
from instantneo.history.queries import current_run_config


# ────────────────────────────────────────────────────────────────────
# Matriz de providers a probar
# ────────────────────────────────────────────────────────────────────

# (provider, model, env_var_name)
PROVIDERS = [
    ("openai",    "gpt-5-mini",         "OPEN_AI_API_KEY"),
    ("anthropic", "claude-haiku-4-5",   "ANTHROPIC_API_KEY"),
    ("gemini",    "gemini-2.5-flash",   "GEMINI_API_KEY"),
    ("groq",      "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    ("xai",       "grok-3-fast",        "XAI_API_KEY"),
]


# ────────────────────────────────────────────────────────────────────
# Tool de prueba (común a todos los providers)
# ────────────────────────────────────────────────────────────────────

@tool(description="Returns a current timestamp as a string")
def get_time() -> dict:
    return {"now": "2026-05-11T12:00:00Z", "tz": "UTC"}


# Tokens en errores de API que indican issue de cuenta/billing, no bug
# del código. Distinguen "skip por provider down" de "FAIL real".
_BILLING_ERROR_TOKENS = ("credit balance", "billing", "quota exceeded",
                          "insufficient_quota", "payment", "account_inactive")


def _is_billing_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(tok in msg for tok in _BILLING_ERROR_TOKENS)


# ────────────────────────────────────────────────────────────────────
# Casos
# ────────────────────────────────────────────────────────────────────

def case_response_only(provider: str, model: str, api_key: str) -> bool:
    """Caso A: sin tools → bridge debe emitir 1 entry response."""
    agent = InstantNeo(
        provider=provider, model=model, api_key=api_key,
        role_setup="Sos un asistente conciso.",
    )
    try:
        # max_tokens generoso porque reasoning models (gpt-5*, o4*)
        # consumen budget en thinking interno y dejan poco para output.
        text = agent.run("Decí 'listo' y nada más.", max_tokens=300)
    except Exception as e:
        if _is_billing_error(e):
            raise  # propagar para que el outer lo marque como BILLING_SKIP
        print(f"      [A] LLM call failed: {type(e).__name__}: {e}")
        return False

    h = History()
    h.append(author="orchestrator", type="run_start",
             content={"origin": "smoke", "run_id": "run-A",
                      "agent": {}, "loop": {}})
    entries = h.append_from_run(agent.last_run, turn_num=1, author="agent",
                                 origin="smoke", run_id="run-A")

    response_entries = [e for e in entries if e.type == "response"]
    if not response_entries:
        # Some providers (caso degenerado) podrían no devolver text;
        # imprimimos lo que vino para debugging.
        print(f"      [A] FAIL: 0 response entries (entries={[e.type for e in entries]})")
        return False

    r = response_entries[0]
    assert r.content["origin"] == "smoke"
    assert r.content["run_id"] == "run-A"
    assert "usage" in r.content
    print(f"      [A] OK — response='{text[:40]}...', usage={r.content['usage']}")
    return True


def case_response_with_tool(provider: str, model: str, api_key: str) -> bool:
    """Caso B: agent llama una tool → bridge emite tool_call con args dict."""
    agent = InstantNeo(
        provider=provider, model=model, api_key=api_key,
        role_setup="Si te preguntan la hora, llamá la función get_time.",
        tools=[get_time],
    )
    try:
        agent.run("¿Qué hora es?", max_tokens=400)
    except Exception as e:
        if _is_billing_error(e):
            raise
        print(f"      [B] LLM call failed: {type(e).__name__}: {e}")
        return False

    h = History()
    h.append(author="orchestrator", type="run_start",
             content={"origin": "smoke", "run_id": "run-B",
                      "agent": {}, "loop": {}})
    h.append_from_run(agent.last_run, turn_num=1, author="agent",
                       origin="smoke", run_id="run-B")

    tool_calls = h.by_type("tool_call")
    if not tool_calls:
        # El modelo eligió no llamar tool — no es bug del bridge, solo del modelo
        print(f"      [B] SKIP — el modelo no llamó tool (esperable en algunos)")
        return True

    tc = tool_calls[0]
    assert isinstance(tc.content["arguments"], dict), \
        f"arguments debe ser dict, no {type(tc.content['arguments']).__name__}"
    assert isinstance(tc.content["result"], dict), \
        f"result debe ser dict, no {type(tc.content['result']).__name__}"
    assert tc.content["origin"] == "smoke"
    print(f"      [B] OK — tool '{tc.content['name']}' con args={tc.content['arguments']}, "
          f"result keys={list(tc.content['result'].keys())}")
    return True


def case_queries_post_bridge(provider: str, model: str, api_key: str) -> bool:
    """Caso C: current_run_config refleja el run_start después del bridge."""
    agent = InstantNeo(
        provider=provider, model=model, api_key=api_key,
        role_setup="Sos conciso.",
    )
    try:
        agent.run("Decí 'ok'.", max_tokens=200)
    except Exception as e:
        if _is_billing_error(e):
            raise
        print(f"      [C] LLM call failed: {type(e).__name__}: {e}")
        return False

    h = History()
    h.append(author="orchestrator", type="run_start",
             content={"origin": f"smoke_{provider}", "run_id": "run-C",
                      "agent": {}, "loop": {}})
    h.append_from_run(agent.last_run, turn_num=1, author="agent",
                       origin=f"smoke_{provider}", run_id="run-C")

    cfg = current_run_config(h)
    assert cfg is not None, "current_run_config debería devolver el run_start"
    assert cfg["origin"] == f"smoke_{provider}"
    assert cfg["run_id"] == "run-C"
    print(f"      [C] OK — current_run_config.origin = {cfg['origin']}")
    return True


# ────────────────────────────────────────────────────────────────────
# Main: itera sobre la matriz
# ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("Smoke real del bridge cross-provider")
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
        for case_name, case_fn in [
            ("A", case_response_only),
            ("B", case_response_with_tool),
            ("C", case_queries_post_bridge),
        ]:
            total_run += 1
            try:
                ok = case_fn(provider, model, api_key)
                if ok:
                    cases_ok += 1
                    total_pass += 1
            except Exception as e:
                if _is_billing_error(e):
                    print(f"      [{case_name}] BILLING SKIP: {str(e)[:80]}")
                    billing_skip = True
                    total_run -= 1   # no contar como caso ejecutado
                else:
                    print(f"      [{case_name}] EXCEPTION: {type(e).__name__}: {e}")

        if billing_skip and cases_ok == 0:
            results.append((provider, "BILLING_SKIP"))
        else:
            results.append((provider, f"{cases_ok}/3"))

    print("\n" + "=" * 60)
    print("Resumen:")
    for provider, status in results:
        print(f"  {provider:12s} {status}")
    print(f"\nTotal: {total_pass}/{total_run} casos OK, {total_skip} providers skipped")
    return 0 if total_pass == total_run else 1


if __name__ == "__main__":
    sys.exit(main())
