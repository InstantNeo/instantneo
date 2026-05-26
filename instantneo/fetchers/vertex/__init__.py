"""
Providers hosteados en Vertex AI.

Estructura:
- _auth: VertexAuthMixin compartido (auth GCP + endpoint + headers)
- anthropic: VertexAnthropicClient (Claude)
- gemini: VertexGeminiClient (Gemini)
"""

from instantneo.fetchers.vertex.anthropic import VertexAnthropicClient
from instantneo.fetchers.vertex.gemini import VertexGeminiClient

__all__ = [
    "VertexAnthropicClient",
    "VertexGeminiClient",
]
