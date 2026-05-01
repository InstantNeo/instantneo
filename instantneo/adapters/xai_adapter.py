"""
Adapter para xAI Grok API directa.

Hereda toda la traducción StandardRequest ↔ chat/completions de
`adapters/_chat_completions.ChatCompletionsAdapter`.

Nota: xAI valida `reasoning_effort` con valores `low` o `high` (no
`medium`). El padre pasa el effort tal cual viene en
`request.reasoning.effort`. Si InstantNeo recibe `medium` y se usa xAI,
xAI devolverá un 400. Es comportamiento intencional para que el error
sea visible y no se haga remapping silencioso.
"""

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.xai import XAIClient


class XAIAdapter(ChatCompletionsAdapter):
    """Adapter para xAI Grok API directa (chat/completions)."""

    def __init__(self, api_key: str):
        self.client = XAIClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "xai"
