"""
Validacion funcional de InstantNeo
====================================
Prueba los features core de instantloop-v2 con llamadas reales al LLM.
Funciona con cualquier provider soportado por InstantNeo.

Uso:
    # Auto-detecta provider por la primera API key disponible en el entorno
    python validate.py

    # Provider explicito
    python validate.py --provider groq --model llama-3.3-70b-versatile
    python validate.py --provider openai --model gpt-4.1-mini
    python validate.py --provider anthropic --model claude-haiku-4-5-20251001
    python validate.py --provider cerebras --model llama-3.3-70b
    python validate.py --provider xai --model grok-3-mini
    python validate.py --provider deepseek --model deepseek-chat
    python validate.py --provider mistral --model mistral-small-latest
    python validate.py --provider qwen --model qwen-plus
    python validate.py --provider kimi --model kimi-k2.6
    python validate.py --provider zhipu --model glm-4.5-flash
    python validate.py --provider mimo --model mimo-v2.5-pro

    # Sobrescribir modelo/key sin tocar el provider detectado
    python validate.py --model openai/gpt-oss-20b
    python validate.py --api-key sk-...

Variables de entorno reconocidas para auto-deteccion:
    GROQ_API_KEY, OPEN_AI_API_KEY, OPENAI_API_KEY,
    ANTHROPIC_API_KEY, CEREBRAS_API_KEY, XAI_API_KEY,
    DEEPSEEK_API_KEY, MISTRAL_API_KEY, QWEN_API_KEY, DASHSCOPE_API_KEY,
    KIMI_API_KEY, MOONSHOT_API_KEY,
    ZHIPU_API_KEY, ZAI_API_KEY, GLM_API_KEY,
    MIMO_API_KEY, XIAOMI_MIMO_API_KEY

Variables para configuracion explicita:
    INSTANTNEO_PROVIDER, INSTANTNEO_MODEL, INSTANTNEO_API_KEY

Que valida:
    1. InstantNeo basico         - un solo .run() sin loop
    2. InstantLoop + stop_tool   - loop multi-turno con tool de cierre
    3. History + bridge          - append_entry_from_run
    4. Monitor custom            - regla externa dispara stop_signal
    5. AgentCapabilities         - tools empaquetadas en un objeto reutilizable
"""

import argparse
import os
import sys
from pathlib import Path

# UTF-8 en stdout/stderr para evitar UnicodeEncodeError en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env", override=True)
except ImportError:
    env_path = _REPO_ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

# ── Configuracion de providers ────────────────────────────────────────────────

# (provider, env_var_para_api_key, modelo_default)
_PROVIDERS = [
    ("groq",      "GROQ_API_KEY",      "llama-3.3-70b-versatile"),
    ("openai",    "OPEN_AI_API_KEY",   "gpt-4.1-mini"),
    ("openai",    "OPENAI_API_KEY",    "gpt-4.1-mini"),
    ("anthropic", "ANTHROPIC_API_KEY", "claude-haiku-4-5-20251001"),
    ("cerebras",  "CEREBRAS_API_KEY",  "llama-3.3-70b"),
    ("xai",       "XAI_API_KEY",       "grok-3-mini"),
    ("deepseek",  "DEEPSEEK_API_KEY",  "deepseek-chat"),
    ("mistral",   "MISTRAL_API_KEY",   "mistral-small-latest"),
    ("qwen",      "QWEN_API_KEY",      "qwen-plus"),
    ("qwen",      "DASHSCOPE_API_KEY", "qwen-plus"),
    ("kimi",      "KIMI_API_KEY",      "kimi-k2.6"),
    ("kimi",      "MOONSHOT_API_KEY",  "kimi-k2.6"),
    ("moonshot",  "KIMI_API_KEY",      "kimi-k2.6"),
    ("moonshot",  "MOONSHOT_API_KEY",  "kimi-k2.6"),
    ("zhipu",     "ZHIPU_API_KEY",     "glm-4.5-flash"),
    ("zhipu",     "ZAI_API_KEY",       "glm-4.5-flash"),
    ("zhipu",     "GLM_API_KEY",       "glm-4.5-flash"),
    ("glm",       "ZHIPU_API_KEY",     "glm-4.5-flash"),
    ("glm",       "ZAI_API_KEY",       "glm-4.5-flash"),
    ("glm",       "GLM_API_KEY",       "glm-4.5-flash"),
    ("mimo",      "MIMO_API_KEY",      "mimo-v2.5-pro"),
    ("mimo",      "XIAOMI_MIMO_API_KEY", "mimo-v2.5-pro"),
    ("xiaomi_mimo", "MIMO_API_KEY",    "mimo-v2.5-pro"),
    ("xiaomi_mimo", "XIAOMI_MIMO_API_KEY", "mimo-v2.5-pro"),
]

_DEFAULT_MODEL = {
    "groq":      "llama-3.3-70b-versatile",
    "openai":    "gpt-4.1-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "cerebras":  "llama-3.3-70b",
    "xai":       "grok-3-mini",
    "deepseek":  "deepseek-chat",
    "mistral":   "mistral-small-latest",
    "qwen":      "qwen-plus",
    "kimi":      "kimi-k2.6",
    "moonshot":  "kimi-k2.6",
    "zhipu":     "glm-4.5-flash",
    "glm":       "glm-4.5-flash",
    "mimo":      "mimo-v2.5-pro",
    "xiaomi_mimo": "mimo-v2.5-pro",
}

_KNOWN_KEY_ENV_VARS = sorted({env_var for _, env_var, _ in _PROVIDERS})
_KNOWN_PROVIDERS = sorted(_DEFAULT_MODEL.keys())


def _autodetect() -> tuple[str, str, str]:
    """Devuelve (provider, model, api_key) desde el entorno."""
    for provider, env_var, default_model in _PROVIDERS:
        key = os.environ.get(env_var, "")
        if key:
            return provider, default_model, key
    return "", "", ""


def _key_for_provider(provider: str) -> tuple[str, str]:
    """Devuelve (model_default, api_key) para un provider explicito."""
    provider = provider.lower()
    for item_provider, env_var, default_model in _PROVIDERS:
        if item_provider != provider:
            continue
        key = os.environ.get(env_var, "")
        if key:
            return default_model, key
    return _DEFAULT_MODEL.get(provider, ""), ""


def _resolve_config(args) -> tuple[str, str, str]:
    """Combina CLI args + env vars + autodeteccion. Aborta si faltan datos."""
    provider = args.provider or os.environ.get("INSTANTNEO_PROVIDER", "")
    model    = args.model    or os.environ.get("INSTANTNEO_MODEL", "")
    api_key  = args.api_key  or os.environ.get("INSTANTNEO_API_KEY", "")

    provider = provider.lower()

    if provider and not api_key:
        provider_default_model, provider_key = _key_for_provider(provider)
        model = model or provider_default_model
        api_key = provider_key

    if not provider and not api_key:
        auto_provider, auto_model, auto_key = _autodetect()
        provider = provider or auto_provider
        model    = model    or auto_model
        api_key  = api_key  or auto_key

    if not provider or not api_key:
        print(
            "ERROR: no se encontro provider ni API key.\n"
            "Exporta una de:\n"
            f"                {', '.join(_KNOWN_KEY_ENV_VARS)}\n"
            "o usa --provider y --api-key."
        )
        sys.exit(1)

    model = model or _DEFAULT_MODEL.get(provider, "")
    if not model:
        print(f"ERROR: no se pudo determinar un modelo por defecto para provider '{provider}'.")
        print("Usa --model <nombre>.")
        sys.exit(1)

    return provider, model, api_key


# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Validacion funcional de InstantNeo")
parser.add_argument(
    "--provider",
    default="",
    help=f"Provider ({', '.join(_KNOWN_PROVIDERS)})",
)
parser.add_argument("--model",    default="", help="Nombre del modelo a usar")
parser.add_argument("--api-key",  default="", dest="api_key", help="API key del provider")
args = parser.parse_args()

PROVIDER, MODEL, API_KEY = _resolve_config(args)

# ── Imports de InstantNeo ─────────────────────────────────────────────────────

from instantneo import (
    InstantNeo, InstantLoop, History, Monitor,
    tool, AgentCapabilities,
    append_entry_from_run,
)
from instantneo.monitor.conditions import when_last_tool_called
from instantneo.monitor.actions import stop_signal

class RequiredToolLoop(InstantLoop):
    """Loop de validacion que fuerza tool-calling en cada step."""

    def _invoke_agent(self, text: str, images, image_detail) -> None:
        self.agent.run(
            text,
            images=images,
            image_detail=image_detail,
            tool_choice="required",
        )

# ── Helpers de reporte ────────────────────────────────────────────────────────

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, cond, detail))
    status = "PASS" if cond else "FAIL"
    line = f"  [{status}]  {name}"
    if detail:
        line += f" -- {detail}"
    print(line)


def sep(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 60 - len(title) - 4))


# ── Banner ────────────────────────────────────────────────────────────────────

print(f"\nInstantNeo validate.py")
print(f"  provider : {PROVIDER}")
print(f"  model    : {MODEL}")


# =============================================================================
# TEST 1 -- InstantNeo basico (un solo run, sin loop)
# agent.run() retorna el texto; RunInfo queda en agent.last_run
# =============================================================================

sep("TEST 1: InstantNeo basico")

try:
    agent_simple = InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup="Eres un asistente conciso.",
        max_tokens=256,
    )
    text = agent_simple.run("Responde exactamente con esta frase, sin nada mas: INSTANTNEO_OK")
    run_info = agent_simple.last_run

    check("run() retorna string", isinstance(text, str), repr(str(text)[:60]))
    check("last_run tiene response_content",
          run_info is not None and run_info.response_content is not None)
    check("respuesta contiene INSTANTNEO_OK", "INSTANTNEO_OK" in (text or ""), repr(str(text)[:80]))
    check("usage registrado", run_info is not None and run_info.usage.get("total_tokens", 0) > 0)

except Exception as e:
    check("TEST 1 sin excepcion", False, str(e))


# =============================================================================
# TEST 2 -- InstantLoop + stop_tool (multi-turno)
# =============================================================================

sep("TEST 2: InstantLoop + stop_tool")

NUMEROS = [7, 14, 3, 22, 9, 1]
MAXIMO_ESPERADO = max(NUMEROS)


@tool(
    description="Devuelve la lista de numeros disponibles para analizar.",
    parameters={},
)
def obtener_numeros() -> list:
    return NUMEROS


@tool(
    description="Reporta el numero maximo encontrado. Llamar cuando hayas terminado el analisis.",
    parameters={
        "maximo": {"description": "El numero maximo de la lista.", "type": "integer"},
        "razon":  {"description": "Breve justificacion.", "type": "string"},
    },
)
def reportar_maximo(maximo, razon: str) -> dict:
    try:
        maximo = int(maximo)
    except (TypeError, ValueError):
        pass
    return {"maximo": maximo, "correcto": maximo == MAXIMO_ESPERADO}


try:
    agent_loop = InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup=(
            "Eres un analista de datos. Tu tarea:\n"
            "1. Llama a `obtener_numeros` para obtener la lista.\n"
            "2. Identifica el numero mas alto.\n"
            "3. Llama a `reportar_maximo` con el resultado.\n"
            "No respondas en texto plano, usa siempre las tools."
        ),
        tools=[obtener_numeros, reportar_maximo],
        max_tokens=512,
    )

    loop = RequiredToolLoop(
        agent=agent_loop,
        name="val_loop",
        stop_tool="reportar_maximo",
        max_steps=8,
    )

    result = loop.run("Analiza los numeros y reporta el maximo.")

    check("loop termino por stop_signal",
          result.terminated_reason == "stop_signal",
          f"reason={result.terminated_reason}")
    check("uso mas de 1 step", result.total_steps >= 2, f"steps={result.total_steps}")
    check("history tiene entries", len(result.history.all()) > 0)

    tool_calls = result.history.by_type("tool_call")
    tool_names = [tc.content.get("name") for tc in tool_calls]
    check("llamo a obtener_numeros",  "obtener_numeros"  in tool_names)
    check("llamo a reportar_maximo",  "reportar_maximo"  in tool_names)

    for tc in tool_calls:
        if tc.content.get("name") == "reportar_maximo":
            args = tc.content.get("arguments", {})
            raw = args.get("maximo") if isinstance(args, dict) else None
            try:
                maximo_reportado = int(raw)
            except (TypeError, ValueError):
                maximo_reportado = raw
            check("reporto el maximo correcto (22)",
                  maximo_reportado == MAXIMO_ESPERADO,
                  f"reportado={maximo_reportado!r}")
            break

except Exception as e:
    check("TEST 2 sin excepcion", False, str(e))


# =============================================================================
# TEST 3 -- History standalone + bridge append_entry_from_run
# API: append_entry_from_run(history, run_info, *, turn_num, author, origin, run_id)
# =============================================================================

sep("TEST 3: History + bridge append_entry_from_run")

try:
    agent_h = InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup="Responde siempre en una sola palabra.",
        max_tokens=32,
    )
    agent_h.run("Responde solo la palabra: VERDE")
    run_info_h = agent_h.last_run

    history = History()
    append_entry_from_run(
        history,
        run_info_h,
        turn_num=1,
        author="agente_test",
        origin="validacion",
        run_id="test-run-001",
    )

    entries = history.all()
    types_present = {e.type for e in entries}
    check("history tiene entries tras bridge", len(entries) > 0, f"types={types_present}")
    check("entry tipo 'response' presente",  "response"  in types_present)
    check("entry tipo 'tool_call' ausente",  "tool_call" not in types_present)

    responses = history.by_type("response")
    if responses:
        content_val = responses[0].content.get("text", "")
        check("response.text tiene contenido", bool(content_val), repr(str(content_val)[:60]))

except Exception as e:
    check("TEST 3 sin excepcion", False, str(e))


# =============================================================================
# TEST 4 -- Monitor con regla custom
# Monitor no recibe history en constructor; se asocia al loop via monitors=[...]
# El loop necesita stop_signals=["texto"] como whitelist para reconocer la senal
# =============================================================================

sep("TEST 4: Monitor con regla custom")

try:
    @tool(
        description="Senala que terminaste de reflexionar sobre la respuesta.",
        parameters={
            "pensamiento": {"description": "Resumen breve de lo que pensaste.", "type": "string"},
        },
    )
    def pensar(pensamiento: str) -> dict:
        return {"ok": True}

    agent_mon = InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup=(
            "Eres un agente reflexivo. "
            "Cuando termines de responder, llama siempre a `pensar` con un breve resumen."
        ),
        tools=[pensar],
        max_tokens=512,
    )

    history_mon = History()
    monitor = Monitor(name="monitor_pensar")
    monitor.add_rule(
        when_last_tool_called("pensar"),
        stop_signal("agente llamo a pensar"),
    )

    loop_mon = RequiredToolLoop(
        agent=agent_mon,
        name="val_monitor",
        history=history_mon,
        monitors=[monitor],
        stop_signals=["agente llamo a pensar"],
        max_steps=6,
    )

    result_mon = loop_mon.run("Cual es la capital de Francia? Luego llama a pensar.")

    check("loop termino por stop_signal",
          result_mon.terminated_reason == "stop_signal",
          f"reason={result_mon.terminated_reason}")
    check("stop_reason menciona 'pensar'",
          "pensar" in (result_mon.stop_reason or ""),
          f"stop_reason={result_mon.stop_reason!r}")
    check("history compartido tiene entries", len(history_mon.all()) > 0)

except Exception as e:
    check("TEST 4 sin excepcion", False, str(e))


# =============================================================================
# TEST 5 -- AgentCapabilities (tools empaquetadas)
# InstantNeo acepta AgentCapabilities via tools= (no capabilities=)
# La libreria NO hace coercion de tipos: las tools deben convertir ellas mismas
# =============================================================================

sep("TEST 5: AgentCapabilities")

try:
    @tool(
        description="Convierte temperatura de Celsius a Fahrenheit.",
        parameters={
            "celsius": {"description": "Temperatura en Celsius.", "type": "number"},
        },
    )
    def celsius_a_fahrenheit(celsius) -> dict:
        return {"fahrenheit": round(float(celsius) * 9 / 5 + 32, 2)}

    @tool(
        description="Entrega el resultado final de la conversion. Llamar cuando tengas el resultado.",
        parameters={
            "resultado": {"description": "Temperatura en Fahrenheit.", "type": "number"},
        },
    )
    def entregar(resultado) -> dict:
        return {"entregado": float(resultado)}

    caps = AgentCapabilities(
        skills=[celsius_a_fahrenheit, entregar],
        global_instructions=(
            "Debes usar siempre las tools disponibles, nunca texto plano. "
            "Primero llama a celsius_a_fahrenheit, luego a entregar con el resultado."
        ),
    )

    cap_names = set(caps.get_tool_names())
    check("capabilities registra celsius_a_fahrenheit", "celsius_a_fahrenheit" in cap_names)
    check("capabilities registra entregar",             "entregar"             in cap_names)

    agent_caps = InstantNeo(
        provider=PROVIDER,
        model=MODEL,
        api_key=API_KEY,
        role_setup=(
            "Eres un conversor de temperaturas. "
            "Para convertir: llama a celsius_a_fahrenheit y luego a entregar."
        ),
        tools=caps,
        max_tokens=1024,
    )

    loop_caps = RequiredToolLoop(
        agent=agent_caps,
        name="val_caps",
        stop_tool="entregar",
        max_steps=8,
    )

    result_caps = loop_caps.run("Convierte 100 grados Celsius a Fahrenheit y entrega el resultado.")

    check("loop termino por stop_signal",
          result_caps.terminated_reason == "stop_signal",
          f"reason={result_caps.terminated_reason}")

    tc_caps  = result_caps.history.by_type("tool_call")
    names_caps = [tc.content.get("name") for tc in tc_caps]
    check("llamo a celsius_a_fahrenheit", "celsius_a_fahrenheit" in names_caps)
    check("llamo a entregar",             "entregar"             in names_caps)

    for tc in tc_caps:
        if tc.content.get("name") == "entregar":
            args = tc.content.get("arguments", {})
            raw = args.get("resultado") if isinstance(args, dict) else None
            try:
                resultado_num = float(raw)
            except (TypeError, ValueError):
                resultado_num = raw
            check("resultado correcto (212 F)", resultado_num == 212.0,
                  f"resultado={resultado_num!r}")
            break

except Exception as e:
    check("TEST 5 sin excepcion", False, str(e))


# =============================================================================
# Resumen final
# =============================================================================

total  = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

print(f"\n{'=' * 60}")
print(f"RESULTADO FINAL: {passed}/{total} checks pasaron")
if failed:
    print("\nFALLIDOS:")
    for name, ok, detail in results:
        if not ok:
            print(f"  [FAIL]  {name}" + (f" -- {detail}" if detail else ""))
print(f"{'=' * 60}\n")

sys.exit(0 if failed == 0 else 1)
