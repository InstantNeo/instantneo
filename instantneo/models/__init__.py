"""
Modelos de datos para proveedores de LLM.

Este módulo contiene todos los tipos de datos (dataclasses) para interactuar
con diferentes APIs de LLM, organizados por proveedor.

NOTA SOBRE EL ORDEN DE IMPORTS:
`models/groq.py` re-exporta tipos definidos en `models/_chat_completions.py`.
Si algún día reordenas los imports de abajo, asegúrate de que
`_chat_completions` (importado dentro de `groq.py`) puede cargar antes de
que cualquier código fuera de `models/` empiece a tocar el paquete
`instantneo.fetchers`. Romperlo causa un `ImportError` por ciclo:
fetchers/__init__.py → fetchers/groq.py → models/groq.py (a medio cargar).
Si necesitas verificar, corre `python tests/test_imports.py`.
"""

# Tipos estándar (interfaz unificada Core <-> Adapters)
from .standard import (
    # Content blocks
    TextContent,
    ImageContent,
    ContentBlock,
    # Tools
    StandardTool,
    StandardToolChoice,
    StandardToolCall,
    # Messages
    StandardMessage,
    # Request/Response
    StandardRequest,
    StandardResponse,
    StandardChoice,
    StandardResponseMessage,
    StandardUsage,
    # Streaming
    StandardStreamDelta,
    StandardStreamChunk,
    # Factory helpers
    create_user_message,
    create_system_message,
    create_assistant_message,
    create_tool_result_message,
    create_tool,
)


# Tipos específicos de Anthropic
from .anthropic import (
    MessageContent,
    Message as AnthropicMessage,
    Tool as AnthropicTool,
    CacheControl,
    ContentBlock,
    Usage as AnthropicUsage,
    AnthropicResponse,
    AnthropicError,
)

# Tipos específicos de OpenAI
from .openai import (
    InputText,
    InputImage,
    InputFile,
    InputAudioData,
    InputAudio,
    InputMessage,
    FunctionTool,
    FileSearchTool,
    WebSearchTool,
    CodeInterpreterTool,
    ComputerUseTool,
    ImageGenerationTool,
    TextFormat,
    JsonSchemaFormat,
    JsonObjectFormat,
    TextConfig,
    ReasoningConfig,
    StreamOptions,
    PromptReference,
    Conversation,
    OutputText,
    ToolCall as OpenAIToolCall,
    Reasoning,
    OutputMessage,
    UsageDetails,
    Usage as OpenAIUsage,
    IncompleteDetails,
    OpenAIResponse,
    ErrorDetails,
)

# Tipos específicos de Groq
from .groq import (
    Message as GroqMessage,
    ToolFunction,
    Tool as GroqTool,
    Document,
    SearchSettings,
    FunctionCall,
    ToolCall as GroqToolCall,
    ResponseMessage,
    Choice,
    Usage as GroqUsage,
    GroqResponse,
    GroqError,
)

# Tipos de metadata de ejecución
from .run_info import (
    SkillExecution,
    LLMCall,
    RunInfo,
)

# Tipos específicos de Cerebras
from .cerebras import (
    Message as CerebrasMessage,
    ToolFunction as CerebrasToolFunction,
    Tool as CerebrasTool,
    Prediction as CerebrasPrediction,
    FunctionCall as CerebrasFunctionCall,
    ToolCall as CerebrasToolCall,
    ResponseMessage as CerebrasResponseMessage,
    Choice as CerebrasChoice,
    Usage as CerebrasUsage,
    PromptTokensDetails,
    CompletionTokensDetails,
    TimeInfo,
    CerebrasResponse,
    CerebrasError,
)

__all__ = [
    # Standard types (interfaz unificada)
    "TextContent",
    "ImageContent",
    "ContentBlock",
    "StandardTool",
    "StandardToolChoice",
    "StandardToolCall",
    "StandardMessage",
    "StandardRequest",
    "StandardResponse",
    "StandardChoice",
    "StandardResponseMessage",
    "StandardUsage",
    "StandardStreamDelta",
    "StandardStreamChunk",
    "create_user_message",
    "create_system_message",
    "create_assistant_message",
    "create_tool_result_message",
    "create_tool",

    # Anthropic types
    "MessageContent",
    "AnthropicMessage",
    "AnthropicTool",
    "CacheControl",
    "ContentBlock",
    "AnthropicUsage",
    "AnthropicResponse",
    "AnthropicError",

    # OpenAI types
    "InputText",
    "InputImage",
    "InputFile",
    "InputAudioData",
    "InputAudio",
    "InputMessage",
    "FunctionTool",
    "FileSearchTool",
    "WebSearchTool",
    "CodeInterpreterTool",
    "ComputerUseTool",
    "ImageGenerationTool",
    "TextFormat",
    "JsonSchemaFormat",
    "JsonObjectFormat",
    "TextConfig",
    "ReasoningConfig",
    "StreamOptions",
    "PromptReference",
    "Conversation",
    "OutputText",
    "OpenAIToolCall",
    "Reasoning",
    "OutputMessage",
    "UsageDetails",
    "OpenAIUsage",
    "IncompleteDetails",
    "OpenAIResponse",
    "ErrorDetails",

    # Groq types
    "GroqMessage",
    "ToolFunction",
    "GroqTool",
    "Document",
    "SearchSettings",
    "FunctionCall",
    "GroqToolCall",
    "ResponseMessage",
    "Choice",
    "GroqUsage",
    "GroqResponse",
    "GroqError",

    # Cerebras types
    "CerebrasMessage",
    "CerebrasToolFunction",
    "CerebrasTool",
    "CerebrasPrediction",
    "CerebrasFunctionCall",
    "CerebrasToolCall",
    "CerebrasResponseMessage",
    "CerebrasChoice",
    "CerebrasUsage",
    "PromptTokensDetails",
    "CompletionTokensDetails",
    "TimeInfo",
    "CerebrasResponse",
    "CerebrasError",

    # Run info types
    "SkillExecution",
    "LLMCall",
    "RunInfo",
]
