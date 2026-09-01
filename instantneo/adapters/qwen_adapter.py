"""Adapter para Qwen / Alibaba Cloud Model Studio."""

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.qwen import QwenClient


class QwenAdapter(ChatCompletionsAdapter):
    """Adapter para Qwen via Model Studio compatible mode."""

    def __init__(self, api_key: str):
        self.client = QwenClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "qwen"
