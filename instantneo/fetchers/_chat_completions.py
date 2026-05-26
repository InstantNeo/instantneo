"""
Base interna para clientes HTTP de providers OpenAI chat/completions.

Encapsula la mecánica HTTP genérica del formato chat/completions clásico,
que comparten Groq, xAI, Mistral, DeepSeek, Together AI, Fireworks,
Perplexity, y los modelos third-party de Vertex AI Model Garden.

Clase concreta vive en cada provider:
    fetchers/groq.py     → GroqClient(ChatCompletionsClient)
    fetchers/xai.py      → XAIClient(ChatCompletionsClient)
    fetchers/vertex/xai.py → VertexXAIClient(VertexAuthMixin, XAIClient)

El módulo lleva prefijo "_" para señalizar que es base interna; no se
instancia directamente, no se expone como provider público.
"""

from typing import Any, Dict, Iterator, List, Optional
import httpx
import json

# Tipos del wire format viven en models/ para evitar ciclos de import
# (fetchers/__init__.py importa de fetchers/groq.py que importa de models).
from instantneo.models._chat_completions import (  # noqa: F401 (re-export)
    ChatCompletionResponse,
    Choice,
    FunctionCall,
    Message,
    ResponseMessage,
    Tool,
    ToolCall,
    ToolFunction,
    Usage,
)


# ============================================================================
# CLIENTE BASE
# ============================================================================

# Params chat/completions estándar que la base sabe nombrar explícitamente.
# Los kwargs adicionales (reasoning_format, search_parameters, documents,
# search_settings, deferred, etc.) se pasan al body en passthrough.
_STANDARD_BODY_PARAMS = (
    "temperature",
    "max_tokens",
    "max_completion_tokens",
    "top_p",
    "stop",
    "seed",
    "n",
    "stream",
    "stream_options",
    "tool_choice",
    "parallel_tool_calls",
    "response_format",
    "reasoning_effort",
    "user",
    "service_tier",
)


class ChatCompletionsClient:
    """
    Cliente HTTP base para providers OpenAI chat/completions.

    Subclases declaran:
        BASE_URL = "https://provider.com/v1/chat/completions"

    Hooks sobrescribibles:
        _build_headers()   — auth headers (default Bearer)
        _get_url(model, stream) — URL del endpoint (default self.BASE_URL)
        _build_request_body(messages, model, **kwargs) — construye body
        _parse_response(data) — parsea response no-stream
        _validate_request(messages, model, **kwargs) — pre-validación

    No se instancia directamente.
    """

    BASE_URL: str = ""  # subclase debe declarar
    DEFAULT_TIMEOUT = 600.0

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT):
        if type(self) is ChatCompletionsClient:
            raise TypeError(
                "ChatCompletionsClient es una clase base interna; "
                "usa una subclase concreta (GroqClient, XAIClient, etc.)."
            )
        if not self.BASE_URL:
            raise NotImplementedError(
                f"{type(self).__name__} debe declarar BASE_URL como atributo de clase."
            )
        self.api_key = api_key
        self.timeout = timeout

    # ─── Hooks sobrescribibles ──────────────────────────────────────────────

    def _build_headers(self) -> Dict[str, str]:
        """Headers HTTP. Override en Vertex para Bearer token de OAuth."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _get_url(self, model: str, stream: bool = False) -> str:
        """URL del endpoint. Override en Vertex Model Garden."""
        return self.BASE_URL

    def _validate_request(self, messages: List[Message], model: str, **kwargs) -> None:
        """Pre-validación. Default no hace nada. Groq override para sus límites."""
        pass

    def _serialize_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Serializa mensajes al formato wire chat/completions."""
        out = []
        for msg in messages:
            entry: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            for k, v in (
                ("name", msg.name),
                ("tool_calls", msg.tool_calls),
                ("tool_call_id", msg.tool_call_id),
            ):
                if v is not None:
                    entry[k] = v
            out.append(entry)
        return out

    def _serialize_tools(self, tools: List[Tool]) -> List[Dict[str, Any]]:
        """Serializa tools al formato OpenAI function calling."""
        return [
            {
                "type": tool.type,
                "function": {
                    "name": tool.function.name,
                    "description": tool.function.description,
                    "parameters": tool.function.parameters,
                },
            }
            for tool in tools
        ]

    def _build_request_body(
        self,
        messages: List[Message],
        model: str,
        tools: Optional[List[Tool]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Construye el body chat/completions estándar.

        Los kwargs estándar OpenAI se incluyen si no son None.
        Cualquier kwarg adicional (reasoning_format, search_parameters,
        documents, search_settings, deferred, etc.) se pasa tal cual al
        body — esto permite que cada provider añada sus propios campos
        sin que la base tenga que conocerlos.
        """
        body: Dict[str, Any] = {
            "model": model,
            "messages": self._serialize_messages(messages),
        }

        if tools is not None:
            body["tools"] = self._serialize_tools(tools)

        for key, value in kwargs.items():
            if value is None:
                continue
            body[key] = value

        return body

    def _parse_response(self, data: Dict[str, Any]) -> ChatCompletionResponse:
        """Parsea response chat/completions a tipos genéricos."""
        choices = []
        for choice_data in data.get("choices", []):
            msg_data = choice_data.get("message", {})

            tool_calls = None
            if msg_data.get("tool_calls"):
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        type=tc["type"],
                        function=FunctionCall(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"],
                        ),
                    )
                    for tc in msg_data["tool_calls"]
                ]

            message = ResponseMessage(
                role=msg_data.get("role", "assistant"),
                content=msg_data.get("content"),
                tool_calls=tool_calls,
                refusal=msg_data.get("refusal"),
                reasoning=msg_data.get("reasoning"),
            )

            choices.append(Choice(
                index=choice_data.get("index", 0),
                message=message,
                finish_reason=choice_data.get("finish_reason", "stop"),
                logprobs=choice_data.get("logprobs"),
            ))

        usage_data = data.get("usage", {}) or {}
        completion_details = usage_data.get("completion_tokens_details") or {}
        prompt_details = usage_data.get("prompt_tokens_details") or {}
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            prompt_time=usage_data.get("prompt_time"),
            completion_time=usage_data.get("completion_time"),
            total_time=usage_data.get("total_time"),
            reasoning_tokens=completion_details.get("reasoning_tokens"),
            cached_tokens=prompt_details.get("cached_tokens"),
        )

        return ChatCompletionResponse(
            id=data.get("id", ""),
            object=data.get("object", "chat.completion"),
            created=data.get("created", 0),
            model=data.get("model", ""),
            choices=choices,
            usage=usage,
            system_fingerprint=data.get("system_fingerprint"),
            usage_breakdown=data.get("usage_breakdown"),
        )

    # ─── API pública del cliente ─────────────────────────────────────────────

    def create_chat_completion(
        self,
        messages: List[Message],
        model: str,
        tools: Optional[List[Tool]] = None,
        **kwargs,
    ) -> ChatCompletionResponse:
        """
        Crea una completion non-stream. Pasa kwargs tal cual al body.

        Kwargs estándar OpenAI: temperature, max_tokens, max_completion_tokens,
        top_p, stop, seed, tool_choice, parallel_tool_calls, response_format,
        reasoning_effort, user, service_tier, n.

        Kwargs provider-specific también pasan: reasoning_format,
        search_parameters, documents, search_settings, deferred, etc.
        """
        # Forzar stream=False
        kwargs.pop("stream", None)
        self._validate_request(messages, model, tools=tools, **kwargs)
        headers = self._build_headers()
        body = self._build_request_body(messages=messages, model=model, tools=tools, **kwargs)
        body.pop("stream", None)  # no-stream
        url = self._get_url(model, stream=False)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=body)

            if response.status_code != 200:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", str(error_data))
                except Exception:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                raise httpx.HTTPStatusError(
                    f"{type(self).__name__} error: {error_msg}",
                    request=response.request,
                    response=response,
                )

            return self._parse_response(response.json())

    def create_chat_completion_stream(
        self,
        messages: List[Message],
        model: str,
        tools: Optional[List[Tool]] = None,
        **kwargs,
    ) -> Iterator[Dict[str, Any]]:
        """
        Crea una completion streaming. Yields dicts con eventos SSE.

        Default `stream_options={"include_usage": True}` para que el último
        chunk traiga usage (Groq y la mayoría de providers OpenAI-compat
        lo soportan).
        """
        # Forzar stream=True
        kwargs["stream"] = True
        kwargs.setdefault("stream_options", {"include_usage": True})
        self._validate_request(messages, model, tools=tools, **kwargs)
        headers = self._build_headers()
        body = self._build_request_body(messages=messages, model=model, tools=tools, **kwargs)
        url = self._get_url(model, stream=True)

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", url, headers=headers, json=body) as response:
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
