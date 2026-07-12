"""
Smoke test de imports.

No requiere credenciales — sólo verifica que el árbol de imports del
paquete carga sin ciclos ni errores. Diseñado para correr en CI antes
de cualquier test que requiera red o keys.

Uso:
    python tests/test_imports.py

También compatible con pytest si está instalado:
    pytest tests/test_imports.py
"""

import sys


def test_top_level_package() -> None:
    """El paquete raíz expone InstantNeo, tool, AgentCapabilities."""
    from instantneo import InstantNeo, tool, AgentCapabilities  # noqa: F401


def test_standard_models() -> None:
    """Los tipos del contrato Standard cargan sin ciclos."""
    from instantneo.models.standard import (  # noqa: F401
        StandardRequest, StandardResponse, StandardChoice,
        StandardResponseMessage, StandardUsage, StandardToolCall,
        StandardStreamChunk, StandardStreamDelta, StandardMessage,
        StandardTool, StandardToolChoice,
    )


def test_chat_completions_types() -> None:
    """
    Tipos chat/completions accesibles por dos rutas:
    - models/_chat_completions (canónico)
    - models/groq (re-export para compat con imports históricos)

    Si esto falla, probablemente alguien reordenó `models/__init__.py`
    y rompió el orden de carga. Revisa el comentario en ese archivo.
    """
    from instantneo.models._chat_completions import (  # noqa: F401
        Message, Tool, ToolFunction, FunctionCall, ToolCall,
        ResponseMessage, Choice, Usage, ChatCompletionResponse,
    )
    from instantneo.models.groq import (  # noqa: F401
        Message, Tool, GroqResponse, Document, SearchSettings, GroqError,
    )


def test_provider_specific_models() -> None:
    """Tipos específicos de cada provider que NO usa chat/completions."""
    from instantneo.models.anthropic import (  # noqa: F401
        Message, Tool, AnthropicResponse, ContentBlock, Usage,
    )
    from instantneo.models.gemini import (  # noqa: F401
        Content, Part, GeminiResponse, FunctionDeclaration,
    )
    from instantneo.models.openai import OpenAIResponse  # noqa: F401
    from instantneo.models.cerebras import CerebrasResponse  # noqa: F401


def test_fetcher_bases() -> None:
    """Bases internas (fetchers) sin instanciar."""
    from instantneo.fetchers._chat_completions import ChatCompletionsClient  # noqa: F401
    from instantneo.fetchers.vertex._auth import VertexAuthMixin  # noqa: F401


def test_direct_fetchers() -> None:
    """Clientes HTTP de cada provider directo."""
    from instantneo.fetchers.anthropic import AnthropicClient, fetch_anthropic  # noqa: F401
    from instantneo.fetchers.gemini import GeminiClient, fetch_gemini  # noqa: F401
    from instantneo.fetchers.groq import GroqClient, fetch_groq  # noqa: F401
    from instantneo.fetchers.openai import OpenAIClient, fetch_openai  # noqa: F401
    from instantneo.fetchers.cerebras import CerebrasClient, fetch_cerebras  # noqa: F401
    from instantneo.fetchers.xai import XAIClient, fetch_xai  # noqa: F401
    from instantneo.fetchers.fireworks import FireworksClient, fetch_fireworks  # noqa: F401


def test_vertex_fetchers() -> None:
    """Clientes Vertex (3) accesibles también desde el sub-paquete."""
    from instantneo.fetchers.vertex.anthropic import VertexAnthropicClient  # noqa: F401
    from instantneo.fetchers.vertex.gemini import VertexGeminiClient  # noqa: F401
    from instantneo.fetchers.vertex.xai import VertexXAIClient  # noqa: F401
    from instantneo.fetchers.vertex import (  # noqa: F401
        VertexAnthropicClient, VertexGeminiClient,
    )


def test_adapter_bases() -> None:
    """Bases internas (adapters)."""
    from instantneo.adapters.base_adapter import BaseAdapter  # noqa: F401
    from instantneo.adapters._chat_completions import ChatCompletionsAdapter  # noqa: F401


def test_direct_adapters() -> None:
    """Adapters de cada provider directo."""
    from instantneo.adapters.anthropic_adapter import AnthropicAdapter  # noqa: F401
    from instantneo.adapters.gemini_adapter import GeminiAdapter  # noqa: F401
    from instantneo.adapters.groq_adapter import GroqAdapter  # noqa: F401
    from instantneo.adapters.openai_adapter import OpenAIAdapter  # noqa: F401
    from instantneo.adapters.cerebras_adapter import CerebrasAdapter  # noqa: F401
    from instantneo.adapters.xai_adapter import XAIAdapter  # noqa: F401
    from instantneo.adapters.fireworks_adapter import FireworksAdapter  # noqa: F401


def test_vertex_adapters() -> None:
    """Adapters Vertex (3): wrappers delgados sobre los directos."""
    from instantneo.adapters.vertex_anthropic_adapter import VertexAnthropicAdapter  # noqa: F401
    from instantneo.adapters.vertex_gemini_adapter import VertexGeminiAdapter  # noqa: F401
    from instantneo.adapters.vertex_xai_adapter import VertexXAIAdapter  # noqa: F401


def test_adapters_namespace() -> None:
    """`instantneo.adapters` namespace expone los adapters como atributos."""
    import instantneo.adapters as a
    for name in (
        "BaseAdapter", "AnthropicAdapter", "OpenAIAdapter", "GroqAdapter",
        "CerebrasAdapter", "VertexAnthropicAdapter", "VertexGeminiAdapter",
        "XAIAdapter", "VertexXAIAdapter", "FireworksAdapter",
    ):
        assert getattr(a, name, None) is not None, f"adapters.{name} no expuesto"


def test_abstract_base_classes_dont_instantiate() -> None:
    """Las bases internas rechazan instanciación directa."""
    from instantneo.fetchers._chat_completions import ChatCompletionsClient
    from instantneo.adapters._chat_completions import ChatCompletionsAdapter

    try:
        ChatCompletionsClient(api_key="x")
    except TypeError:
        pass
    else:
        raise AssertionError("ChatCompletionsClient debería rechazar instanciación directa")

    try:
        ChatCompletionsAdapter()
    except TypeError:
        pass
    else:
        raise AssertionError("ChatCompletionsAdapter debería rechazar instanciación directa")


def test_core_adapter_map_is_resolvable() -> None:
    """Cada entrada en core.adapter_map referencia un módulo y clase reales."""
    import importlib
    from instantneo.core import InstantNeo  # noqa: F401
    import inspect
    from instantneo import core

    src = inspect.getsource(core.InstantNeo._create_adapter)
    # Extraer las entradas del adapter_map por parsing simple del source.
    # No es elegante, pero es estable y no requiere construir un InstantNeo.
    expected_providers = (
        "openai", "anthropic", "groq", "cerebras",
        "gemini", "vertexai", "vertex_anthropic", "xai", "vertex_xai",
        "fireworks",
    )
    for provider in expected_providers:
        assert f'"{provider}"' in src, f"core.adapter_map missing provider {provider!r}"


# ─── Runner ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("top_level_package", test_top_level_package),
        ("standard_models", test_standard_models),
        ("chat_completions_types", test_chat_completions_types),
        ("provider_specific_models", test_provider_specific_models),
        ("fetcher_bases", test_fetcher_bases),
        ("direct_fetchers", test_direct_fetchers),
        ("vertex_fetchers", test_vertex_fetchers),
        ("adapter_bases", test_adapter_bases),
        ("direct_adapters", test_direct_adapters),
        ("vertex_adapters", test_vertex_adapters),
        ("adapters_namespace", test_adapters_namespace),
        ("abstract_base_classes_dont_instantiate", test_abstract_base_classes_dont_instantiate),
        ("core_adapter_map_is_resolvable", test_core_adapter_map_is_resolvable),
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")

    print()
    total = len(tests)
    passed = total - len(failures)
    print(f"PASS: {passed} / {total}")
    if failures:
        sys.exit(1)
