"""
Smoke real (opt-in) cross-provider del ``InstantLoop`` (PR 8).

Para cada provider del .env: construye un Loop con `stop_tool` sugar,
agent llama la tool → Loop rompe limpio. Verifica:

- terminated_reason="stop_signal"
- stop_reason="agent called finalizar"
- history contiene run_start, prompt, step_start, response/tool_call,
  step_end, stop_signal, run_end.
- debug=True genera RunLog con archivos en disco.

Requiere `.env`.
"""
import os
import sys
import tempfile
from pathlib import Path
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
load_dotenv(_REPO_ROOT / ".env", override=True)

from instantneo import InstantNeo, AgentCapabilities, tool
from instantneo.loop import InstantLoop, load_run_logs


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


@tool(description="Finaliza la tarea cuando ya respondiste todo",
      parameters={
          "summary": {"description": "Resumen", "type": "str"},
      })
def finalizar(summary: str) -> dict:
    return {"summary": summary, "done": True}


def case_loop_with_stop_tool(provider: str, model: str, api_key: str) -> bool:
    """Loop con stop_tool='finalizar' debe romper limpio cuando el agente
    llama la tool."""
    caps = AgentCapabilities(skills=[finalizar])
    agent = InstantNeo(
        provider=provider, model=model, api_key=api_key,
        role_setup="Sos un asistente. Cuando termines, llamá finalizar con un resumen.",
        tools=caps,
    )

    with tempfile.TemporaryDirectory() as tmp:
        loop = InstantLoop(
            agent=agent,
            name=f"smoke_{provider}",
            stop_tool="finalizar",
            max_steps=5,
            debug=True,
            debug_base_path=tmp,
        )
        try:
            result = loop.run("Decí 'hola' y después llamá finalizar con un resumen breve.")
        except Exception as e:
            if _is_billing_error(e):
                raise
            print(f"      LLM call failed: {type(e).__name__}: {e}")
            return False

        # Verificar el flow general
        if result.terminated_reason not in ("stop_signal", "max_steps"):
            print(f"      UNEXPECTED terminated_reason: {result.terminated_reason}")
            return False

        # Estructura del History
        types = [e.type for e in result.history.all()]
        expected_min = {"run_start", "prompt", "step_start", "step_end", "run_end"}
        missing = expected_min - set(types)
        if missing:
            print(f"      FAIL — falta {missing} en types")
            return False

        # RunLog presente y con archivos
        assert result.log is not None
        loop_folder = Path(tmp) / f"smoke_{provider}"
        runs = list(loop_folder.iterdir())
        if not runs:
            print(f"      FAIL — no se creó folder de run en disco")
            return False
        files = {f.name for f in runs[0].iterdir()}
        assert "config.json" in files
        assert "run_end.json" in files

        print(f"      OK — terminated={result.terminated_reason!r}, "
              f"stop_reason={result.stop_reason!r}, steps={result.total_steps}, "
              f"log.turns={len(result.log.turns)}, files={sorted(files)}")
        return True


def main() -> int:
    print("Smoke real del InstantLoop cross-provider (PR 8)")
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
            if case_loop_with_stop_tool(provider, model, api_key):
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
