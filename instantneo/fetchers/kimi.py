"""
Fetcher para Kimi / Moonshot AI API.

Kimi expone un endpoint chat/completions compatible con OpenAI, servido por
Moonshot AI en https://api.moonshot.ai/v1/chat/completions.
"""

from typing import Any, Dict, Iterator, List, Union

from instantneo.fetchers._chat_completions import (
    ChatCompletionsClient,
    ChatCompletionResponse,
    Message,
)


class KimiClient(ChatCompletionsClient):
    """Cliente HTTP para Kimi / Moonshot AI API."""

    BASE_URL = "https://api.moonshot.ai/v1/chat/completions"


KimiResponse = ChatCompletionResponse


def fetch_kimi(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    **kwargs,
) -> Union[ChatCompletionResponse, Iterator[Dict[str, Any]]]:
    """Funcion de conveniencia para hacer requests a Kimi / Moonshot AI."""
    client = KimiClient(api_key=api_key)
    if stream:
        return client.create_chat_completion_stream(
            messages=messages, model=model, **kwargs
        )
    return client.create_chat_completion(
        messages=messages, model=model, **kwargs
    )
