"""
Adapter para Fireworks AI API.

Hereda toda la traducción StandardRequest ↔ chat/completions de
`adapters/_chat_completions.ChatCompletionsAdapter`.

Los parámetros propios de Fireworks (top_k, min_p, repetition_penalty,
prompt_truncate_len, context_length_exceeded_behavior, etc.) llegan vía
`provider_params` y el padre los pasa al body en passthrough.
"""

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.fireworks import FireworksClient


class FireworksAdapter(ChatCompletionsAdapter):
    """Adapter para Fireworks AI API (chat/completions)."""

    def __init__(self, api_key: str):
        self.client = FireworksClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "fireworks"
