"""
Fetchers para proveedores de LLM.

Este módulo contiene clientes HTTP puros para interactuar con diferentes
proveedores de modelos de lenguaje, sin depender de sus SDKs oficiales.
"""

from .anthropic import fetch_anthropic
from .openai import fetch_openai
from .groq import fetch_groq
from .cerebras import fetch_cerebras
from .vertex_anthropic import VertexAnthropicClient

__all__ = [
    "fetch_anthropic",
    "fetch_openai",
    "fetch_groq",
    "fetch_cerebras",
    "VertexAnthropicClient",
]
