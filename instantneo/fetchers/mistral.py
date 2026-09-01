"""
Fetcher para Mistral AI API.

Mistral ofrece un endpoint chat/completions con estructura compatible con
OpenAI. Las extensiones propias del provider pasan por kwargs al body.
"""

from typing import Any, Dict, Iterator, List, Union

from instantneo.fetchers._chat_completions import (
    ChatCompletionsClient,
    ChatCompletionResponse,
    Message,
)


class MistralClient(ChatCompletionsClient):
    """Cliente HTTP para Mistral AI API."""

    BASE_URL = "https://api.mistral.ai/v1/chat/completions"


MistralResponse = ChatCompletionResponse


def fetch_mistral(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    **kwargs,
) -> Union[ChatCompletionResponse, Iterator[Dict[str, Any]]]:
    """Funcion de conveniencia para hacer requests a Mistral AI API."""
    client = MistralClient(api_key=api_key)
    if stream:
        return client.create_chat_completion_stream(
            messages=messages, model=model, **kwargs
        )
    return client.create_chat_completion(
        messages=messages, model=model, **kwargs
    )
