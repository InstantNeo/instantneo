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

# Intentar importar CerebrasAdapter si está disponible
try:
    from .cerebras_adapter import CerebrasAdapter
    __all__.append('CerebrasAdapter')
except ImportError:
    CerebrasAdapter = None

try:
    from .vertex_anthropic_adapter import VertexAnthropicAdapter
    __all__.append('VertexAnthropicAdapter')
except ImportError:
    VertexAnthropicAdapter = None

try:
    from .vertex_gemini_adapter import VertexGeminiAdapter
    __all__.append('VertexGeminiAdapter')
except ImportError:
    VertexGeminiAdapter = None

try:
    from .xai_adapter import XAIAdapter
    __all__.append('XAIAdapter')
except ImportError:
    XAIAdapter = None

try:
    from .vertex_xai_adapter import VertexXAIAdapter
    __all__.append('VertexXAIAdapter')
except ImportError:
    VertexXAIAdapter = None

try:
    from .fireworks_adapter import FireworksAdapter
    __all__.append('FireworksAdapter')
except ImportError:
    FireworksAdapter = None
