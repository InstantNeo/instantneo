"""
Adapter para xAI Grok hosteado en Vertex AI Model Garden.

Reutiliza toda la lógica de traducción de XAIAdapter (que a su vez
hereda de ChatCompletionsAdapter), solo cambia el cliente HTTP.
"""

from typing import Any, Dict, Optional

from instantneo.adapters.xai_adapter import XAIAdapter
from instantneo.fetchers.vertex.xai import VertexXAIClient


class VertexXAIAdapter(XAIAdapter):
    """Adapter para xAI Grok vía Vertex Model Garden."""

    def __init__(
        self,
        location: str = "global",
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ):
        # NO llamar a super().__init__() — necesitamos otro cliente.
        self.client = VertexXAIClient(
            location=location,
            service_account_file=service_account_file,
            service_account_info=service_account_info,
            access_token=access_token,
        )

    def get_provider_name(self) -> str:
        return "vertex_xai"
