"""
Fetcher para Qwen / Alibaba Cloud Model Studio.

Qwen se consume via el "compatible mode" OpenAI de Model Studio. El default
usa el endpoint internacional; otras regiones se pueden agregar luego como
configuracion publica si hace falta.
"""

from typing import Any, Dict, Iterator, List, Union

from instantneo.fetchers._chat_completions import (
    ChatCompletionsClient,
    ChatCompletionResponse,
    Message,
)


class QwenClient(ChatCompletionsClient):
    """Cliente HTTP para Qwen via Model Studio compatible mode."""

    BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"


QwenResponse = ChatCompletionResponse


def fetch_qwen(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    **kwargs,
) -> Union[ChatCompletionResponse, Iterator[Dict[str, Any]]]:
    """Funcion de conveniencia para hacer requests a Qwen."""
    client = QwenClient(api_key=api_key)
    if stream:
        return client.create_chat_completion_stream(
            messages=messages, model=model, **kwargs
        )
    return client.create_chat_completion(
        messages=messages, model=model, **kwargs
    )
