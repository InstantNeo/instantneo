"""Adapter para Xiaomi MiMo API."""

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.mimo import MiMoClient


class MiMoAdapter(ChatCompletionsAdapter):
    """Adapter para Xiaomi MiMo API (chat/completions)."""

    def __init__(self, api_key: str):
        self.client = MiMoClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "mimo"
