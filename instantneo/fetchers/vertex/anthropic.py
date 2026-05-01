"""
Cliente HTTP para Anthropic Claude hosteado en Vertex AI.

Hereda toda la lógica del provider (request body, parsing, streaming) de
AnthropicClient y solo cambia el transporte (auth + endpoint + body delta)
vía VertexAuthMixin.

Diferencias vs Anthropic directo:
- Auth: OAuth Bearer token desde Service Account (no x-api-key)
- Endpoint: publishers/anthropic/models/{model}:{rawPredict|streamRawPredict}
- Body: se omite "model" (va en URL) y se añade "anthropic_version"
"""

from typing import Any, Dict, Optional

from instantneo.fetchers.anthropic import AnthropicClient
from instantneo.fetchers.vertex._auth import VertexAuthMixin


class VertexAnthropicClient(VertexAuthMixin, AnthropicClient):
    """Cliente HTTP para Claude vía Vertex AI."""

    PUBLISHER = "anthropic"
    ANTHROPIC_VERSION = "vertex-2023-10-16"

    def __init__(
        self,
        location: str,
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
        timeout: float = VertexAuthMixin.DEFAULT_TIMEOUT,
    ):
        # Inicializa el transporte Vertex (auth + project_id + timeout).
        # AnthropicClient.__init__ no se llama: requiere api_key, que aquí no aplica.
        VertexAuthMixin.__init__(
            self,
            location=location,
            service_account_file=service_account_file,
            service_account_info=service_account_info,
            access_token=access_token,
            timeout=timeout,
        )

    def _build_headers(self, anthropic_version: str = "2023-06-01") -> Dict[str, str]:
        # En Vertex la versión va en el body, no en el header.
        return self._build_vertex_headers()

    def _get_url(self, model: str, stream: bool = False) -> str:
        action = "streamRawPredict" if stream else "rawPredict"
        return self._vertex_endpoint(self.PUBLISHER, model, action)

    def _build_request_body(self, model: str, **kwargs) -> Dict[str, Any]:
        body = super()._build_request_body(model=model, **kwargs)
        body.pop("model", None)
        body["anthropic_version"] = self.ANTHROPIC_VERSION
        return body
