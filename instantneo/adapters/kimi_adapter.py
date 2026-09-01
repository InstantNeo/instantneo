"""Adapter para Kimi / Moonshot AI API."""

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.kimi import KimiClient


class KimiAdapter(ChatCompletionsAdapter):
    """Adapter para Kimi / Moonshot AI API (chat/completions)."""

    def __init__(self, api_key: str):
        self.client = KimiClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "kimi"
