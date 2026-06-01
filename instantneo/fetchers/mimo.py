"""
Fetcher para Xiaomi MiMo API.

MiMo documenta una API chat/completions OpenAI-compatible. El header Bearer
del cliente base es compatible con la documentacion actual.
"""

from typing import Any, Dict, Iterator, List, Union

from instantneo.fetchers._chat_completions import (
    ChatCompletionsClient,
    ChatCompletionResponse,
    Message,
)


class MiMoClient(ChatCompletionsClient):
    """Cliente HTTP para Xiaomi MiMo API."""

    BASE_URL = "https://api.xiaomimimo.com/v1/chat/completions"


MiMoResponse = ChatCompletionResponse


def fetch_mimo(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    **kwargs,
) -> Union[ChatCompletionResponse, Iterator[Dict[str, Any]]]:
    """Funcion de conveniencia para hacer requests a Xiaomi MiMo."""
    client = MiMoClient(api_key=api_key)
    if stream:
        return client.create_chat_completion_stream(
            messages=messages, model=model, **kwargs
        )
    return client.create_chat_completion(
        messages=messages, model=model, **kwargs
    )
