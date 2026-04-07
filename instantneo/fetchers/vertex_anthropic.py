"""
Fetcher para Anthropic Claude en Vertex AI.

Combina la autenticación OAuth de Vertex AI con el formato
de request/response de Anthropic Messages API.

Endpoints:
- Non-streaming: publishers/anthropic/models/{model}:rawPredict
- Streaming: publishers/anthropic/models/{model}:streamRawPredict

Diferencias vs API directa de Anthropic:
- No se envía "model" en el body (ya va en la URL)
- Se agrega "anthropic_version": "vertex-2023-10-16" en el body
- Autenticación via OAuth Bearer token (no x-api-key)
"""

from typing import Any, Dict, List, Optional, Union, Literal, Iterator
import httpx
import json
import time

# Reutilizar autenticación de Vertex AI
from instantneo.fetchers.vertexai import (
    _create_jwt,
    _exchange_jwt_for_token,
    _load_service_account,
)

# Reutilizar modelos de datos de Anthropic
from instantneo.models.anthropic import (
    Message,
    Tool,
    ContentBlock,
    Usage,
    AnthropicResponse,
)


class VertexAnthropicClient:
    """Cliente HTTP para Anthropic Claude vía Vertex AI."""

    DEFAULT_TIMEOUT = 600.0
    TOKEN_EXPIRY_BUFFER = 60
    ANTHROPIC_VERSION = "vertex-2023-10-16"

    def __init__(
        self,
        location: str,
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.location = location
        self.timeout = timeout
        self.project_id: Optional[str] = None

        self._access_token = access_token
        self._token_expiry: Optional[float] = None
        self._sa_info: Optional[Dict[str, Any]] = None

        if service_account_file or service_account_info:
            self._sa_info = _load_service_account(
                service_account_file=service_account_file,
                service_account_info=service_account_info,
            )
            self.project_id = self._sa_info.get("project_id")
        elif not access_token:
            raise ValueError(
                "Debe proporcionar service_account_file, service_account_info, o access_token"
            )

    def _get_access_token(self) -> str:
        """Obtiene un token de acceso válido, refrescando si es necesario."""
        if self._access_token and self._token_expiry is None and self._sa_info is None:
            return self._access_token

        now = time.time()
        if self._access_token and self._token_expiry:
            if now < (self._token_expiry - self.TOKEN_EXPIRY_BUFFER):
                return self._access_token

        if self._sa_info:
            jwt = _create_jwt(
                client_email=self._sa_info["client_email"],
                private_key=self._sa_info["private_key"],
                token_uri=self._sa_info["token_uri"],
            )
            token_data = _exchange_jwt_for_token(jwt, self._sa_info["token_uri"])
            self._access_token = token_data["access_token"]
            self._token_expiry = now + token_data.get("expires_in", 3600)
            return self._access_token

        raise RuntimeError("No hay método de autenticación configurado")

    def _build_headers(self) -> Dict[str, str]:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _get_endpoint(self, model: str, stream: bool = False) -> str:
        action = "streamRawPredict" if stream else "rawPredict"
        return (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/anthropic/models/{model}:{action}"
        )

    def _build_request_body(
        self,
        messages: List[Message],
        max_tokens: int,
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        temperature: Optional[float] = None,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        thinking: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Construye el body. NO incluye model (va en URL). Incluye anthropic_version."""
        body: Dict[str, Any] = {
            "anthropic_version": self.ANTHROPIC_VERSION,
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ],
            "max_tokens": max_tokens,
        }

        if system is not None:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = temperature
        if top_k is not None:
            body["top_k"] = top_k
        if top_p is not None:
            body["top_p"] = top_p
        if stop_sequences is not None:
            body["stop_sequences"] = stop_sequences
        if stream:
            body["stream"] = stream
        if metadata is not None:
            body["metadata"] = metadata
        if tools is not None:
            body["tools"] = [
                {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
                for tool in tools
            ]
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        if thinking is not None:
            body["thinking"] = thinking

        return body

    def _parse_response(self, response_data: Dict[str, Any]) -> AnthropicResponse:
        """Parsea la respuesta JSON. Idéntico al parser de AnthropicClient."""
        content_blocks = []
        for block in response_data.get("content", []):
            content_blocks.append(ContentBlock(
                type=block["type"],
                text=block.get("text"),
                thinking=block.get("thinking"),
                id=block.get("id"),
                name=block.get("name"),
                input=block.get("input"),
            ))

        usage_data = response_data["usage"]
        usage = Usage(
            input_tokens=usage_data["input_tokens"],
            output_tokens=usage_data["output_tokens"],
            cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens"),
            cache_read_input_tokens=usage_data.get("cache_read_input_tokens"),
        )

        return AnthropicResponse(
            id=response_data.get("id", ""),
            type=response_data.get("type", "message"),
            role=response_data.get("role", "assistant"),
            content=content_blocks,
            model=response_data.get("model", ""),
            stop_reason=response_data.get("stop_reason"),
            stop_sequence=response_data.get("stop_sequence"),
            usage=usage,
        )

    def create_message(
        self,
        model: str,
        messages: List[Message],
        max_tokens: int,
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        temperature: Optional[float] = None,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        thinking: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> AnthropicResponse:
        """Crea un mensaje usando Claude vía Vertex AI."""
        headers = self._build_headers()
        body = self._build_request_body(
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            stop_sequences=stop_sequences,
            stream=False,
            metadata=metadata,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
        )

        endpoint = self._get_endpoint(model, stream=False)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(endpoint, headers=headers, json=body)

            if response.status_code != 200:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", str(error_data))
                raise httpx.HTTPStatusError(
                    f"Vertex AI Anthropic error: {error_msg}",
                    request=response.request,
                    response=response,
                )

            return self._parse_response(response.json())

    def create_message_stream(
        self,
        model: str,
        messages: List[Message],
        max_tokens: int,
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        temperature: Optional[float] = None,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        thinking: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Iterator[Dict[str, Any]]:
        """Crea un mensaje con streaming usando Claude vía Vertex AI."""
        headers = self._build_headers()
        body = self._build_request_body(
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            stop_sequences=stop_sequences,
            stream=True,
            metadata=metadata,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
        )

        endpoint = self._get_endpoint(model, stream=True)

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", endpoint, headers=headers, json=body) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue
