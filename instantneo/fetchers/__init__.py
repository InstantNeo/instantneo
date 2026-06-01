"""
Fetchers para proveedores de LLM.

Este módulo contiene clientes HTTP puros para interactuar con diferentes
proveedores de modelos de lenguaje, sin depender de sus SDKs oficiales.

Providers directos: anthropic, openai, groq, deepseek, mistral, qwen, kimi,
zhipu, mimo, cerebras, gemini.
Providers en Vertex AI: ver subpaquete `vertex/`.
"""

from .anthropic import fetch_anthropic
from .openai import fetch_openai
from .groq import fetch_groq
from .deepseek import fetch_deepseek
from .mistral import fetch_mistral
from .qwen import fetch_qwen
from .kimi import fetch_kimi
from .zhipu import fetch_zhipu
from .mimo import fetch_mimo
from .cerebras import fetch_cerebras
from .vertex import VertexAnthropicClient, VertexGeminiClient

__all__ = [
    "fetch_anthropic",
    "fetch_openai",
    "fetch_groq",
    "fetch_deepseek",
    "fetch_mistral",
    "fetch_qwen",
    "fetch_kimi",
    "fetch_zhipu",
    "fetch_mimo",
    "fetch_cerebras",
    "VertexAnthropicClient",
    "VertexGeminiClient",
]
