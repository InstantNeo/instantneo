"""InstantNeo Package

This package provides the main interface to access InstantNeo's functionalities.

Easy import:
```python
from instantneo import InstantNeo, tool, AgentCapabilities, CapabilitiesOperations
# Or using backward-compat names:
from instantneo import InstantNeo, skill, SkillManager, SkillManagerOperations
```

Package structure:
- instantneo.InstantNeo: Main class encapsulating InstantNeo's logic.
- instantneo.Tools: Contains utilities related to tools.
    - instantneo.Tools.tool: Decorator to define tools.
    - instantneo.Tools.AgentCapabilities: Tool and capability registry.
    - instantneo.Tools.CapabilitiesOperations: Set operations for capabilities.
- instantneo.Adapters: Contains adapters for different providers.
    - instantneo.Adapters.Groq: Adapter for Groq.
    - instantneo.Adapters.Openai: Adapter for OpenAI.
    - instantneo.Adapters.Anthropic: Adapter for Anthropic.
"""

# Importación de la clase principal
from .core import InstantNeo

# Importación de modelos de metadata de ejecución
from .models.run_info import RunInfo

# New canonical imports
from .skills.tool_decorators import tool
from .skills.agent_capabilities import AgentCapabilities
from .skills.capabilities_operations import CapabilitiesOperations

# Backward compatibility imports
from .skills.tool_decorators import skill
from .skills.agent_capabilities import AgentCapabilities as SkillManager
from .skills.capabilities_operations import CapabilitiesOperations as SkillManagerOperations

# Importaciones para Adapters - Usando importación condicional

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

# New namespace
class Tools:
    """Tools toolkit"""
    tool = tool
    AgentCapabilities = AgentCapabilities
    CapabilitiesOperations = CapabilitiesOperations

# Backward compat namespace
class Skills:
    """Skills toolkit (backward compat alias for Tools)"""
    skill = skill
    SkillManager = SkillManager
    SkillManagerOperations = SkillManagerOperations

# Namespace para Adapters
class Adapters:
    """Adapters for different providers"""
    Groq = GroqAdapter
    Openai = OpenAIAdapter
    Anthropic = AnthropicAdapter

# Definir qué se exporta
__all__ = [
    "InstantNeo", "RunInfo",
    "tool", "AgentCapabilities", "CapabilitiesOperations",
    "skill", "SkillManager", "SkillManagerOperations",
    "Tools", "Skills", "Adapters",
]
