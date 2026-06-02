"""Adapter para Mistral AI API."""

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.mistral import MistralClient


class MistralAdapter(ChatCompletionsAdapter):
    """Adapter para Mistral AI API (chat/completions)."""

    def __init__(self, api_key: str):
        self.client = MistralClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "mistral"
