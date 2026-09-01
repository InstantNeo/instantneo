"""Adapter para Zhipu / GLM / Z.ai."""

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.zhipu import ZhipuClient


class ZhipuAdapter(ChatCompletionsAdapter):
    """Adapter para Zhipu / GLM / Z.ai (chat/completions)."""

    def __init__(self, api_key: str):
        self.client = ZhipuClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "zhipu"
