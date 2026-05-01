"""
Cliente HTTP para xAI Grok hosteado en Vertex AI Model Garden.

Hereda toda la lógica del provider (request body, parsing, streaming SSE)
de XAIClient (que a su vez hereda de ChatCompletionsClient) y solo cambia
el transporte (auth + endpoint + prefijo de modelo) vía VertexAuthMixin.

Diferencias vs xAI directo:
- Auth: OAuth Bearer token desde Service Account (no API key de x.ai).
- Endpoint: Vertex Model Garden OpenAI-compat (endpoints/openapi/chat/completions).
- Modelo: Vertex requiere prefijo "xai/" (ej: "xai/grok-4.1-fast-reasoning").
"""

from typing import Any, Dict, List, Optional

from instantneo.fetchers._chat_completions import Message, Tool
from instantneo.fetchers.vertex._auth import VertexAuthMixin
from instantneo.fetchers.xai import XAIClient


class VertexXAIClient(VertexAuthMixin, XAIClient):
    """Cliente HTTP para xAI Grok vía Vertex Model Garden."""

    PUBLISHER_PREFIX = "xai/"

    def __init__(
        self,
        location: str = "global",
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
        timeout: float = VertexAuthMixin.DEFAULT_TIMEOUT,
    ):
        # XAIClient.__init__ no se llama: requiere api_key, que aquí no aplica.
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

    def _get_url(self, model: str, stream: bool = False) -> str:
        # Model Garden: el modelo va en body, no en URL. La URL es fija.
        return self._vertex_openai_compat_endpoint()

    def _build_request_body(
        self,
        messages: List[Message],
        model: str,
        tools: Optional[List[Tool]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Vertex Model Garden requiere prefijo `xai/` en el modelo."""
        if not model.startswith(self.PUBLISHER_PREFIX):
            model = f"{self.PUBLISHER_PREFIX}{model}"
        return super()._build_request_body(
            messages=messages, model=model, tools=tools, **kwargs
        )
