"""
Fetcher para Groq API.

Hereda toda la mecánica HTTP del formato chat/completions estándar de
`fetchers/_chat_completions.ChatCompletionsClient` y solo añade:
- BASE_URL específica de Groq
- Validaciones Groq-specific (max 128 tools, max 4 stop, n=1, etc.)

Re-exporta los tipos comunes (Message, Tool, etc.) para mantener
compatibilidad con código que importa de `instantneo.fetchers.groq`.
"""

from typing import Any, Dict, Iterator, List, Optional, Union

from instantneo.fetchers._chat_completions import (
    ChatCompletionsClient,
    Message,
    Tool,
    ToolFunction,
    FunctionCall,
    ToolCall,
    ResponseMessage,
    Choice,
    Usage,
    ChatCompletionResponse,
)
# Tipos Groq-específicos que no son parte del wire chat/completions estándar
from instantneo.models.groq import Document, SearchSettings, GroqError


# ============================================================================
# CLIENTE GROQ
# ============================================================================

class GroqClient(ChatCompletionsClient):
    """Cliente HTTP para Groq API."""

    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def _validate_request(self, messages, model, **kwargs) -> None:
        """Validaciones Groq-specific."""
        tools = kwargs.get("tools")
        if tools and len(tools) > 128:
            raise ValueError("Groq soporta máximo 128 herramientas")

        stop = kwargs.get("stop")
        if stop:
            stop_list = [stop] if isinstance(stop, str) else stop
            if len(stop_list) > 4:
                raise ValueError("Groq soporta máximo 4 secuencias de parada")

        if kwargs.get("reasoning_format") and kwargs.get("include_reasoning"):
            raise ValueError(
                "reasoning_format e include_reasoning son mutuamente exclusivos"
            )

        n = kwargs.get("n")
        if n is not None and n != 1:
            raise ValueError("Groq solo soporta n=1")

    def _build_request_body(
        self,
        messages: List[Message],
        model: str,
        tools: Optional[List[Tool]] = None,
        documents: Optional[List[Document]] = None,
        search_settings: Optional[SearchSettings] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Override para serializar Document y SearchSettings (tipos Groq) si vienen.
        El resto delega al padre.
        """
        body = super()._build_request_body(messages=messages, model=model, tools=tools, **kwargs)

        if documents is not None:
            body["documents"] = [
                {"text": doc.text, **({"id": doc.id} if doc.id is not None else {})}
                for doc in documents
            ]

        if search_settings is not None:
            body["search_settings"] = {
                k: v
                for k, v in (
                    ("exclude_domains", search_settings.exclude_domains),
                    ("include_domains", search_settings.include_domains),
                )
                if v is not None
            }

        return body


# Alias retro-compatible. Antes el cliente devolvía `GroqResponse` (definido
# en models/groq.py). Ahora devuelve `ChatCompletionResponse` genérico, que
# es estructuralmente equivalente. Mantenemos el alias para que cualquier
# código existente que haga `isinstance(resp, GroqResponse)` siga compilando.
GroqResponse = ChatCompletionResponse


# ============================================================================
# FUNCIÓN DE CONVENIENCIA
# ============================================================================

def fetch_groq(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    **kwargs,
) -> Union[ChatCompletionResponse, Iterator[Dict[str, Any]]]:
    """
    Función de conveniencia para hacer requests a Groq API.

    Acepta cualquier kwarg estándar de chat/completions más los Groq-specific:
    documents, search_settings, reasoning_format, include_reasoning,
    enable_citations, compound_custom, disable_tool_validation, service_tier.

    Returns:
        ChatCompletionResponse si stream=False
        Iterator[Dict] si stream=True
    """
    client = GroqClient(api_key=api_key)
    if stream:
        return client.create_chat_completion_stream(
            messages=messages, model=model, **kwargs
        )
    return client.create_chat_completion(
        messages=messages, model=model, **kwargs
    )
