"""
Fetcher para Fireworks AI API.

Hereda toda la mecánica HTTP del formato chat/completions estándar de
`fetchers/_chat_completions.ChatCompletionsClient` y solo declara la URL
de Fireworks. Los parámetros específicos de Fireworks (`top_k`, `min_p`,
`repetition_penalty`, `prompt_truncate_len`,
`context_length_exceeded_behavior`, etc.) son simplemente más keys en el
body que la base ya soporta vía passthrough.

Endpoint oficial: https://api.fireworks.ai/inference/v1/chat/completions
Los IDs de modelo usan el formato largo de Fireworks, p.ej.
`accounts/fireworks/models/llama-v3p1-70b-instruct`.
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


class FireworksClient(ChatCompletionsClient):
    """Cliente HTTP para Fireworks AI API."""

    BASE_URL = "https://api.fireworks.ai/inference/v1/chat/completions"


def fetch_fireworks(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    **kwargs,
) -> Union[ChatCompletionResponse, Iterator[Dict[str, Any]]]:
    """
    Función de conveniencia para hacer requests a Fireworks AI API.

    Acepta kwargs estándar chat/completions y los Fireworks-specific:
    top_k, min_p, repetition_penalty, prompt_truncate_len,
    context_length_exceeded_behavior.

    Returns:
        ChatCompletionResponse si stream=False
        Iterator[Dict] si stream=True
    """
    client = FireworksClient(api_key=api_key)
    if stream:
        return client.create_chat_completion_stream(
            messages=messages, model=model, **kwargs
        )
    return client.create_chat_completion(
        messages=messages, model=model, **kwargs
    )
