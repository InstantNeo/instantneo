"""
Fetcher para xAI Grok API directa.

Hereda toda la mecánica HTTP del formato chat/completions estándar de
`fetchers/_chat_completions.ChatCompletionsClient` y solo declara la URL
de xAI. Los parámetros específicos de xAI (`reasoning_effort`,
`search_parameters`, `deferred`, `max_completion_tokens`) son simplemente
más keys en el body que la base ya soporta vía passthrough.

Endpoint oficial: https://api.x.ai/v1/chat/completions
Reasoning effort acepta `low` o `high` (no `medium`).
"""

from typing import Any, Dict, Iterator, List, Union

from instantneo.fetchers._chat_completions import (
    ChatCompletionsClient,
    ChatCompletionResponse,
    Message,
    # Re-exports para uso directo desde este módulo
    Tool,  # noqa: F401
    ToolFunction,  # noqa: F401
    FunctionCall,  # noqa: F401
    ToolCall,  # noqa: F401
    ResponseMessage,  # noqa: F401
    Choice,  # noqa: F401
    Usage,  # noqa: F401
)


class XAIClient(ChatCompletionsClient):
    """Cliente HTTP para xAI Grok API directa."""

    BASE_URL = "https://api.x.ai/v1/chat/completions"


def fetch_xai(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    **kwargs,
) -> Union[ChatCompletionResponse, Iterator[Dict[str, Any]]]:
    """
    Función de conveniencia para hacer requests a xAI Grok API.

    Acepta kwargs estándar chat/completions y los xAI-specific:
    reasoning_effort (low/high), search_parameters, deferred,
    max_completion_tokens.

    Returns:
        ChatCompletionResponse si stream=False
        Iterator[Dict] si stream=True
    """
    client = XAIClient(api_key=api_key)
    if stream:
        return client.create_chat_completion_stream(
            messages=messages, model=model, **kwargs
        )
    return client.create_chat_completion(
        messages=messages, model=model, **kwargs
    )
