"""
Smoke real (opt-in) cross-provider de los nuevos métodos públicos del
PR 6: ``agent.capabilities.get_schemas()`` y
``agent.get_resolved_role_setup()``.

No invoca al LLM — solo verifica que los métodos producen data válida
contra un agente construido para cada provider (las API keys solo
sirven para que el constructor del adapter no rompa; no hay request).

Útil para confirmar:
- El método ``get_schemas`` funciona idéntico cross-provider
  (no depende del provider, solo de AgentCapabilities).
- ``get_resolved_role_setup`` funciona idéntico cross-provider
  (no depende del provider, solo de InstantNeo).

Requiere ``.env`` (las keys se usan para instanciar el agente; si
faltan se skip).

Uso: ``python3 tests/smoke/smoke_agent_introspection.py``
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
load_dotenv(_REPO_ROOT / ".env", override=True)

from instantneo import InstantNeo, AgentCapabilities, tool


PROVIDERS = [
    ("openai",    "gpt-5-mini",        "OPEN_AI_API_KEY"),
    ("anthropic", "claude-haiku-4-5",  "ANTHROPIC_API_KEY"),
    ("gemini",    "gemini-2.5-flash",  "GEMINI_API_KEY"),
    ("groq",      "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    ("xai",       "grok-3-fast",       "XAI_API_KEY"),
]


@tool(description="Get weather for a city", parameters={
    "location": {"description": "City name", "type": "str"},
    "units":    {"description": "Units", "type": "str",
                 "enum": ["c", "f"]},
})
def get_weather(location: str, units: str = "c") -> dict:
    return {"location": location, "units": units, "temp": 22}


@tool(description="Sum two numbers", parameters={
    "a": {"description": "First", "type": "int"},
    "b": {"description": "Second", "type": "int"},
})
def add(a: int, b: int) -> int:
    return a + b


def case_introspection(provider: str, model: str, api_key: str) -> bool:
    caps = AgentCapabilities(skills=[get_weather, add])
    caps.set_global_instructions("\n\nUsá las tools cuando aplique.")

    agent = InstantNeo(
        provider=provider, model=model, api_key=api_key,
        role_setup="Sos un asistente experto.",
        tools=caps,
    )

    # 1. get_schemas
    schemas = agent.capabilities.get_schemas()
    if len(schemas) != 2:
        print(f"      FAIL — get_schemas() devolvió {len(schemas)}, esperaba 2")
        return False
    names = sorted(s["function"]["name"] for s in schemas)
    if names != ["add", "get_weather"]:
        print(f"      FAIL — names esperados ['add', 'get_weather'], got {names}")
        return False

    # 2. get_resolved_role_setup
    resolved = agent.get_resolved_role_setup()
    if not resolved.startswith("Sos un asistente experto."):
        print(f"      FAIL — resolved no comienza con role_setup: {resolved[:80]!r}")
        return False
    if "tools" not in resolved.lower():
        print(f"      FAIL — global_instructions no se reflejó en resolved")
        return False

    # 3. con shelf_context
    resolved_with_shelf = agent.get_resolved_role_setup(
        shelf_context="Contexto activo de prueba."
    )
    if "Contexto activo de prueba." not in resolved_with_shelf:
        print(f"      FAIL — shelf_context no apareció en resolved")
        return False

    # 4. paridad con _prepare_messages
    messages = agent._prepare_messages("hola")
    if messages[0]["content"] != resolved:
        print(f"      FAIL — paridad rota _prepare_messages vs resolved")
        return False

    print(f"      OK — schemas={names}, resolved.len={len(resolved)} chars, "
          f"resolved+shelf.len={len(resolved_with_shelf)} chars")
    return True


def main() -> int:
    print("Smoke cross-provider de introspección (PR 6)")
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
            if case_introspection(provider, model, api_key):
                total_pass += 1
                results.append((provider, "OK"))
            else:
                results.append((provider, "FAIL"))
        except Exception as e:
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
