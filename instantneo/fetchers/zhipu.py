"""
Fetcher para Zhipu / GLM / Z.ai.

La API publica de Z.ai conserva la forma chat/completions, aunque el path no
usa el prefijo /v1 habitual. El cliente base permite declarar la URL completa.
"""

from typing import Any, Dict, Iterator, List, Union

from instantneo.fetchers._chat_completions import (
    ChatCompletionsClient,
    ChatCompletionResponse,
    Message,
)


class ZhipuClient(ChatCompletionsClient):
    """Cliente HTTP para Zhipu / GLM / Z.ai."""

    BASE_URL = "https://api.z.ai/api/paas/v4/chat/completions"


ZhipuResponse = ChatCompletionResponse


def fetch_zhipu(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    **kwargs,
) -> Union[ChatCompletionResponse, Iterator[Dict[str, Any]]]:
    """Funcion de conveniencia para hacer requests a Zhipu / GLM."""
    client = ZhipuClient(api_key=api_key)
    if stream:
        return client.create_chat_completion_stream(
            messages=messages, model=model, **kwargs
        )
    return client.create_chat_completion(
        messages=messages, model=model, **kwargs
    )
