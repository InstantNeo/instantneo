"""
Fetcher para DeepSeek API.

DeepSeek expone un endpoint chat/completions compatible con OpenAI, por lo
que este cliente solo declara la URL del provider y hereda la mecanica HTTP
generica de ChatCompletionsClient.
"""

from typing import Any, Dict, Iterator, List, Union

from instantneo.fetchers._chat_completions import (
    ChatCompletionsClient,
    ChatCompletionResponse,
    Message,
)


class DeepSeekClient(ChatCompletionsClient):
    """Cliente HTTP para DeepSeek API."""

    BASE_URL = "https://api.deepseek.com/chat/completions"


DeepSeekResponse = ChatCompletionResponse


def fetch_deepseek(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    **kwargs,
) -> Union[ChatCompletionResponse, Iterator[Dict[str, Any]]]:
    """Funcion de conveniencia para hacer requests a DeepSeek API."""
    client = DeepSeekClient(api_key=api_key)
    if stream:
        return client.create_chat_completion_stream(
            messages=messages, model=model, **kwargs
        )
    return client.create_chat_completion(
        messages=messages, model=model, **kwargs
    )
