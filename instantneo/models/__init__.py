"""
Modelos de datos para proveedores de LLM.

Este módulo contiene todos los tipos de datos (dataclasses) para interactuar
con diferentes APIs de LLM, organizados por proveedor.
"""

# Tipos comunes/base
from .common import (
    BaseMessage,
    BaseContent,
    BaseToolDefinition,
    BaseToolCall,
    BaseUsage,
    BaseAPIError,
    BaseResponse,
    BaseGenerationParams,
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

__all__ = [
    # Common types
    "BaseMessage",
    "BaseContent",
    "BaseToolDefinition",
    "BaseToolCall",
    "BaseUsage",
    "BaseAPIError",
    "BaseResponse",
    "BaseGenerationParams",

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
]
