"""InstantNeo Package

This package provides the main interface to access InstantNeo's functionalities.

Easy import:
```python
from instantneo import InstantNeo, skill, SkillManager, SkillManagerOperations
```

Package structure:
- instantneo.InstantNeo: Main class encapsulating InstantNeo's logic.
- instantneo.Skills: Contains utilities related to skills.
    - instantneo.Skills.skill: Decorator to define skills.
    - instantneo.Skills.SkillManager: Skills manager.
    - instantneo.Skills.SkillManagerOperations: Additional operations for managing skills and their managers.
- instantneo.Adapters: Contains adapters for different providers.
    - instantneo.Adapters.Groq: Adapter for Groq.
    - instantneo.Adapters.Openai: Adapter for OpenAI.
    - instantneo.Adapters.Anthropic: Adapter for Anthropic.
"""

# Importación de la clase principal
from .core import InstantNeo

# Importaciones para Skills
from .skills.skill_decorators import skill
from .skills.skill_manager import SkillManager
from .skills.skill_manager_operations import SkillManagerOperations

# Importaciones para Adapters - Usando importación condicional

# Intentar importar OpenAIAdapter si está disponible
try:
    from .adapters.openai_adapter import OpenAIAdapter
    # print("OpenAIAdapter importado correctamente")
except ImportError:
    OpenAIAdapter = None

# Intentar importar AnthropicAdapter si está disponible
try:
    from .adapters.anthropic_adapter import AnthropicAdapter
    # print("AnthropicAdapter importado correctamente")
except ImportError:
    AnthropicAdapter = None

# Intentar importar GroqAdapter si está disponible
try:
    from .adapters.groq_adapter import GroqAdapter
    # print("GroqAdapter importado correctamente")
except ImportError:
    GroqAdapter = None

# Después de línea ~25
try:
    from .adapters.gemini_adapter import GeminiAdapter
except ImportError:
    GeminiAdapter = None

# Namespace para Skills
class Skills:
    """Skills toolkit"""
    skill = skill
    SkillManager = SkillManager
    SkillManagerOperations = SkillManagerOperations

# Namespace para Adapters
class Adapters:
    """Adapters for different providers"""
    Groq = GroqAdapter
    Openai = OpenAIAdapter
    Anthropic = AnthropicAdapter
    Gemini = GeminiAdapter

# Definir qué se exporta
__all__ = ["InstantNeo", "Skills", "Adapters"]
