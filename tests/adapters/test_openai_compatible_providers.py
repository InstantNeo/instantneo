"""
Tests para providers OpenAI-compatible agregados sobre ChatCompletionsAdapter.

No hacen red. Verifican que cada adapter:
- use el fetcher correcto y su BASE_URL;
- traduzca tools al wire format chat/completions;
- preserve tool_calls devueltos por el modelo.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.adapters.deepseek_adapter import DeepSeekAdapter
from instantneo.adapters.mistral_adapter import MistralAdapter
from instantneo.adapters.qwen_adapter import QwenAdapter
from instantneo.adapters.kimi_adapter import KimiAdapter
from instantneo.adapters.zhipu_adapter import ZhipuAdapter
from instantneo.adapters.mimo_adapter import MiMoAdapter
from instantneo import InstantNeo
from instantneo.fetchers.deepseek import DeepSeekClient
from instantneo.fetchers.mistral import MistralClient
from instantneo.fetchers.qwen import QwenClient
from instantneo.fetchers.kimi import KimiClient
from instantneo.fetchers.zhipu import ZhipuClient
from instantneo.fetchers.mimo import MiMoClient
from instantneo.fetchers._chat_completions import ChatCompletionsClient
from instantneo.models.standard import (
    StandardMessage,
    StandardRequest,
    StandardTool,
    StandardToolChoice,
)


PROVIDERS = [
    (
        "deepseek",
        DeepSeekAdapter,
        DeepSeekClient,
        "https://api.deepseek.com/chat/completions",
    ),
    (
        "mistral",
        MistralAdapter,
        MistralClient,
        "https://api.mistral.ai/v1/chat/completions",
    ),
    (
        "qwen",
        QwenAdapter,
        QwenClient,
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
    ),
    (
        "kimi",
        KimiAdapter,
        KimiClient,
        "https://api.moonshot.ai/v1/chat/completions",
    ),
    (
        "zhipu",
        ZhipuAdapter,
        ZhipuClient,
        "https://api.z.ai/api/paas/v4/chat/completions",
    ),
    (
        "mimo",
        MiMoAdapter,
        MiMoClient,
        "https://api.xiaomimimo.com/v1/chat/completions",
    ),
]


class CaptureClient:
    def __init__(self):
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return _mk_response()


def _mk_response(tool_args='{"city": "Buenos Aires"}'):
    function = SimpleNamespace(name="get_weather", arguments=tool_args)
    tool_call = SimpleNamespace(id="call_001", function=function)
    message = SimpleNamespace(
        content=None,
        tool_calls=[tool_call],
        reasoning=None,
    )
    choice = SimpleNamespace(message=message, finish_reason="tool_calls", index=0)
    usage = SimpleNamespace(
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
        reasoning_tokens=None,
    )
    return SimpleNamespace(
        id="chatcmpl_test",
        model="test-model",
        choices=[choice],
        usage=usage,
    )


def _mk_request():
    return StandardRequest(
        model="test-model",
        messages=[StandardMessage(role="user", content="Que clima hace?")],
        tools=[
            StandardTool(
                name="get_weather",
                description="Consulta el clima",
                parameters={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                    },
                    "required": ["city"],
                },
            )
        ],
        tool_choice=StandardToolChoice(type="auto"),
        temperature=0.2,
        max_tokens=64,
    )


def test_new_provider_adapters_are_chat_completions_adapters() -> None:
    for provider_name, adapter_cls, client_cls, base_url in PROVIDERS:
        adapter = adapter_cls(api_key="test-key")
        assert isinstance(adapter, ChatCompletionsAdapter)
        assert adapter.get_provider_name() == provider_name
        assert isinstance(adapter.client, client_cls)
        assert adapter.client.BASE_URL == base_url


def test_new_provider_adapters_translate_tools_to_wire_format() -> None:
    for _provider_name, adapter_cls, _client_cls, _base_url in PROVIDERS:
        adapter = adapter_cls(api_key="test-key")
        capture = CaptureClient()
        adapter.client = capture

        standard = adapter.complete(_mk_request())

        assert len(capture.calls) == 1
        call = capture.calls[0]
        assert call["model"] == "test-model"
        assert call["messages"][0].role == "user"
        assert call["tools"][0].type == "function"
        assert call["tools"][0].function.name == "get_weather"
        assert call["tool_choice"] == "auto"

        tool_calls = standard.choices[0].message.tool_calls
        assert tool_calls is not None
        assert tool_calls[0].name == "get_weather"
        assert tool_calls[0].arguments == '{"city": "Buenos Aires"}'
        assert standard.finish_reason == "tool_calls"


def test_new_provider_adapters_normalize_empty_tool_arguments() -> None:
    for _provider_name, adapter_cls, _client_cls, _base_url in PROVIDERS:
        adapter = adapter_cls(api_key="test-key")
        standard = adapter._translate_response(_mk_response(tool_args="null"))
        assert standard.choices[0].message.tool_calls[0].arguments == "{}"


def test_chat_completions_parser_defaults_missing_tool_call_type() -> None:
    """Mistral omite `tool_calls[].type`; el wire default es function."""

    class DummyClient(ChatCompletionsClient):
        BASE_URL = "https://example.invalid/chat/completions"

    client = DummyClient(api_key="test")
    response = client._parse_response({
        "id": "resp_1",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city":"Buenos Aires"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })

    tool_call = response.choices[0].message.tool_calls[0]
    assert tool_call.type == "function"
    assert tool_call.function.name == "get_weather"


def test_instantneo_instantiates_new_providers_and_aliases() -> None:
    cases = [
        ("deepseek", DeepSeekAdapter),
        ("mistral", MistralAdapter),
        ("qwen", QwenAdapter),
        ("kimi", KimiAdapter),
        ("moonshot", KimiAdapter),
        ("zhipu", ZhipuAdapter),
        ("glm", ZhipuAdapter),
        ("mimo", MiMoAdapter),
        ("xiaomi_mimo", MiMoAdapter),
    ]

    for provider, adapter_cls in cases:
        agent = InstantNeo(
            provider=provider,
            api_key="test-key",
            model="test-model",
            role_setup="test",
        )
        assert isinstance(agent.adapter, adapter_cls)
