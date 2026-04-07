"""
Adapter para Anthropic Claude vía Vertex AI.

Reutiliza toda la lógica de traducción de AnthropicAdapter,
solo cambia el cliente HTTP (VertexAnthropicClient en lugar de AnthropicClient).
"""

from typing import Optional, Dict, Any

from instantneo.adapters.anthropic_adapter import AnthropicAdapter
from instantneo.fetchers.vertex_anthropic import VertexAnthropicClient


class VertexAnthropicAdapter(AnthropicAdapter):
    """
    Adapter para Claude en Vertex AI.
    Hereda toda la traducción de AnthropicAdapter.
    """

    def __init__(
        self,
        location: str,
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ):
        # NO llamar a super().__init__() — necesitamos otro cliente
        self.client = VertexAnthropicClient(
            location=location,
            service_account_file=service_account_file,
            service_account_info=service_account_info,
            access_token=access_token,
        )

    def get_provider_name(self) -> str:
        return "vertex_anthropic"
