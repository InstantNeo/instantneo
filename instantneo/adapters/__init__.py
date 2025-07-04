from .base_adapter import BaseAdapter

__all__ = ['BaseAdapter']

# Intentar importar OpenAIAdapter si está disponible
try:
    from .openai_adapter import OpenAIAdapter
    __all__.append('OpenAIAdapter')
except ImportError:
    OpenAIAdapter = None  # Evita errores si se intenta acceder

# Intentar importar AnthropicAdapter si está disponible
try:
    from .anthropic_adapter import AnthropicAdapter
    __all__.append('AnthropicAdapter')
except ImportError:
    AnthropicAdapter = None

# Intentar importar GroqAdapter si está disponible
try:
    from .groq_adapter import GroqAdapter
    __all__.append('GroqAdapter')
except ImportError:
    GroqAdapter = None

# Intentar importar AzureOpenAIAdapter si está disponible
try:
    from .azure_openai_adapter import AzureOpenAIAdapter
    __all__.append('AzureOpenAIAdapter')
except ImportError:
    AzureOpenAIAdapter = None
