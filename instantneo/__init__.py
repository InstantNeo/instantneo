"""InstantNeo Package

Provides the main interface to InstantNeo's functionalities, including
the v2 event-sourced orchestration stack: ``History``, ``Monitor``,
``InstantLoop``, and the bridge ``append_entry_from_run``.

Quickstart (v2 — recomendado):

```python
from instantneo import InstantNeo, History, Monitor, InstantLoop, tool
from instantneo.monitor.actions import stop_signal
from instantneo.monitor.conditions import when_type_present

@tool(description="Finaliza la tarea cuando ya respondiste todo",
      parameters={"summary": {"description": "Resumen", "type": "str"}})
def finalizar(summary: str) -> dict:
    return {"summary": summary, "done": True}

agent = InstantNeo(
    provider="openai", model="gpt-5-mini", api_key="...",
    role_setup="Sos un asistente. Cuando termines, llamá finalizar.",
    tools=[finalizar],
)

loop = InstantLoop(agent=agent, name="my_loop", stop_tool="finalizar")
result = loop.run("explicame qué es la fotosíntesis y luego finalizá")

print(result.terminated_reason)   # "stop_signal"
print(result.stop_reason)          # "agent called finalizar"
```

Quickstart (uso clásico — agente solo, sin Loop):

```python
from instantneo import InstantNeo, tool, AgentCapabilities

@tool(description="...", parameters={...})
def my_tool(...): ...

agent = InstantNeo(provider="openai", model="gpt-5-mini", api_key="...",
                   role_setup="...", tools=[my_tool])
response = agent.run("hola")
```

Public surface (top-level imports):

Existentes:
- ``InstantNeo``: clase principal del agente.
- ``RunInfo``: dataclass de metadata de ejecución.
- ``tool``, ``AgentCapabilities``, ``CapabilitiesOperations``: stack de tools.
- ``Tools``, ``Skills``, ``Adapters``: namespaces de conveniencia.
- ``skill``, ``SkillManager``, ``SkillManagerOperations``: aliases backward-compat.

v2 (event-sourced orchestration):
- ``History``, ``Entry``: log inmutable append-only de entries.
- ``Monitor``: rule engine standalone para reactividad sobre History.
- ``InstantLoop``, ``RunResult``: orquestador multi-turno.
- ``append_entry_from_run``: bridge ``RunInfo → Entries``.
- ``current_run_id``, ``current_origin``, ``current_run_config``,
  ``current_step_num``: queries sobre ``run_start`` / ``step_start``.

Otras piezas (importables vía subpackage, no top-level por minimalismo):
- ``RenderedPrompt``, ``loop_default``: ``from instantneo.loop import ...``
- ``TurnLog``, ``RunLog``: ``from instantneo.debug``,
  ``from instantneo.loop import RunLog``.
- Conditions/actions built-in del Monitor:
  ``from instantneo.monitor.conditions import when_*``,
  ``from instantneo.monitor.actions import stop_signal, append_note``.
- ``MonitorOperations``: ``from instantneo.monitor import MonitorOperations``.

Documentación de diseño: ``docs/design/`` (5 documentos).
"""

# ── Versión (fuente única: pyproject.toml) ──────────────────────────
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("instantneo")
except PackageNotFoundError:  # ejecutando desde el source sin instalar
    __version__ = "0.0.0.dev0"

# ── Logging ─────────────────────────────────────────────────────────
# Patrón estándar de librería: adjuntamos un NullHandler para no emitir
# nada por default. La app consumidora decide handlers/niveles, p.ej.
# logging.getLogger("instantneo").setLevel(logging.DEBUG).
import logging as _logging

_logging.getLogger(__name__).addHandler(_logging.NullHandler())

# ── Core (clásico) ──────────────────────────────────────────────────
from .core import InstantNeo
from .models.run_info import RunInfo

# New canonical imports (tools stack)
from .skills.tool_decorators import tool
from .skills.agent_capabilities import AgentCapabilities
from .skills.capabilities_operations import CapabilitiesOperations

# Backward compatibility imports
from .skills.tool_decorators import skill
from .skills.agent_capabilities import AgentCapabilities as SkillManager
from .skills.capabilities_operations import CapabilitiesOperations as SkillManagerOperations

# Adapters — importación condicional
try:
    from .adapters.openai_adapter import OpenAIAdapter
except ImportError:
    OpenAIAdapter = None

try:
    from .adapters.anthropic_adapter import AnthropicAdapter
except ImportError:
    AnthropicAdapter = None

try:
    from .adapters.groq_adapter import GroqAdapter
except ImportError:
    GroqAdapter = None

try:
    from .adapters.deepseek_adapter import DeepSeekAdapter
except ImportError:
    DeepSeekAdapter = None

try:
    from .adapters.mistral_adapter import MistralAdapter
except ImportError:
    MistralAdapter = None

try:
    from .adapters.qwen_adapter import QwenAdapter
except ImportError:
    QwenAdapter = None

try:
    from .adapters.kimi_adapter import KimiAdapter
except ImportError:
    KimiAdapter = None

try:
    from .adapters.zhipu_adapter import ZhipuAdapter
except ImportError:
    ZhipuAdapter = None

try:
    from .adapters.mimo_adapter import MiMoAdapter
except ImportError:
    MiMoAdapter = None


# ── v2: History + Monitor + Loop + queries + bridge ─────────────────
from .history import History, Entry
from .history.from_run_info import append_entry_from_run
from .history.queries import (
    current_run_id, current_origin, current_run_config, current_step_num,
)
from .monitor import Monitor
from .loop import InstantLoop, RunResult


# ── Namespaces de conveniencia ──────────────────────────────────────

class Tools:
    """Tools toolkit"""
    tool = tool
    AgentCapabilities = AgentCapabilities
    CapabilitiesOperations = CapabilitiesOperations


class Skills:
    """Skills toolkit (backward compat alias for Tools)"""
    skill = skill
    SkillManager = SkillManager
    SkillManagerOperations = SkillManagerOperations


class Adapters:
    """Adapters for different providers"""
    Groq = GroqAdapter
    DeepSeek = DeepSeekAdapter
    Mistral = MistralAdapter
    Qwen = QwenAdapter
    Kimi = KimiAdapter
    Moonshot = KimiAdapter
    Zhipu = ZhipuAdapter
    GLM = ZhipuAdapter
    MiMo = MiMoAdapter
    Openai = OpenAIAdapter
    Anthropic = AnthropicAdapter


# Public surface
__all__ = [
    "__version__",
    # Core (clásico)
    "InstantNeo", "RunInfo",
    "tool", "AgentCapabilities", "CapabilitiesOperations",
    "skill", "SkillManager", "SkillManagerOperations",
    "Tools", "Skills", "Adapters",

    # v2 — event-sourced orchestration
    "History", "Entry",
    "Monitor",
    "InstantLoop", "RunResult",
    "append_entry_from_run",
    "current_run_id", "current_origin",
    "current_run_config", "current_step_num",
]
