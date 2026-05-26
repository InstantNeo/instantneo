"""
Cliente HTTP para Gemini hosteado en Vertex AI.

Hereda toda la lógica del provider (request body, parsing, streaming SSE)
de GeminiClient y solo cambia el transporte (auth + endpoint) vía
VertexAuthMixin.

Diferencias vs Gemini directo (Google AI Studio):
- Auth: OAuth Bearer token desde Service Account (no x-goog-api-key)
- Endpoint: publishers/google/models/{model}:{generateContent|streamGenerateContent}
"""

from typing import Any, Dict, Optional

from instantneo.fetchers.gemini import GeminiClient
from instantneo.fetchers.vertex._auth import VertexAuthMixin


class VertexGeminiClient(VertexAuthMixin, GeminiClient):
    """Cliente HTTP para Gemini vía Vertex AI."""

    PUBLISHER = "google"

    def __init__(
        self,
        location: str,
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
        timeout: float = VertexAuthMixin.DEFAULT_TIMEOUT,
    ):
        # GeminiClient.__init__ no se llama: requiere api_key, que aquí no aplica.
        VertexAuthMixin.__init__(
            self,
            location=location,
            service_account_file=service_account_file,
            service_account_info=service_account_info,
            access_token=access_token,
            timeout=timeout,
        )

    def _build_headers(self) -> Dict[str, str]:
        return self._build_vertex_headers()

    def _get_endpoint(self, model: str, stream: bool = False) -> str:
        action = "streamGenerateContent" if stream else "generateContent"
        url = self._vertex_endpoint(self.PUBLISHER, model, action)
        if stream:
            url += "?alt=sse"
        return url
