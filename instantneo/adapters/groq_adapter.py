"""
Adapter para Groq API.

Hereda toda la traducción StandardRequest ↔ chat/completions de
`adapters/_chat_completions.ChatCompletionsAdapter` y solo declara cómo
instanciar su cliente HTTP y su nombre de provider.
"""

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.groq import GroqClient


class GroqAdapter(ChatCompletionsAdapter):
    """Adapter para Groq API (chat/completions OpenAI-compat)."""

    def __init__(self, api_key: str):
        self.client = GroqClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "groq"
