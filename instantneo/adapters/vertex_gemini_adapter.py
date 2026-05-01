"""
Adapter para Google Gemini hosteado en Vertex AI.

Reutiliza toda la lógica de traducción de GeminiAdapter, solo cambia el
cliente HTTP (VertexGeminiClient en lugar de GeminiClient).
"""

from typing import Any, Dict, Optional

from instantneo.adapters.gemini_adapter import GeminiAdapter
from instantneo.fetchers.vertex.gemini import VertexGeminiClient


class VertexGeminiAdapter(GeminiAdapter):
    """
    Adapter para Gemini en Vertex AI.
    Hereda toda la traducción de GeminiAdapter.
    """

    def __init__(
        self,
        location: str,
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ):
        # NO llamar a super().__init__() — necesitamos otro cliente
        self.client = VertexGeminiClient(
            location=location,
            service_account_file=service_account_file,
            service_account_info=service_account_info,
            access_token=access_token,
        )

    def get_provider_name(self) -> str:
        return "vertexai"
