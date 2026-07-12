"""
Fetchers para proveedores de LLM.

Este módulo contiene clientes HTTP puros para interactuar con diferentes
proveedores de modelos de lenguaje, sin depender de sus SDKs oficiales.

Providers directos: anthropic, openai, groq, cerebras, gemini, xai, fireworks.
Providers en Vertex AI: ver subpaquete `vertex/`.
"""

from .anthropic import fetch_anthropic
from .openai import fetch_openai
from .groq import fetch_groq
from .cerebras import fetch_cerebras
from .xai import fetch_xai
from .fireworks import fetch_fireworks
from .vertex import VertexAnthropicClient, VertexGeminiClient

__all__ = [
    "fetch_anthropic",
    "fetch_openai",
    "fetch_groq",
    "fetch_cerebras",
    "fetch_xai",
    "fetch_fireworks",
    "VertexAnthropicClient",
    "VertexGeminiClient",
]
