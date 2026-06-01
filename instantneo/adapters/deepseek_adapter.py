"""Adapter para DeepSeek API."""

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.deepseek import DeepSeekClient


class DeepSeekAdapter(ChatCompletionsAdapter):
    """Adapter para DeepSeek API (chat/completions OpenAI-compatible)."""

    def __init__(self, api_key: str):
        self.client = DeepSeekClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "deepseek"
