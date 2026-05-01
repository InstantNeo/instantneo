"""
Tipos del wire format OpenAI chat/completions clásico.

Compartidos entre Groq, xAI, Mistral, DeepSeek y otros providers
OpenAI-compat que usen el endpoint chat/completions. Re-exportados desde
`instantneo.models.groq` para mantener compat de imports históricos.

Módulo prefijado con "_" para señalizar que es shared/internal — los
imports públicos viven en `models/groq.py`.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Union


@dataclass
class Message:
    """
    Mensaje en la conversación (formato OpenAI chat/completions).

    El campo `content` puede ser un string simple o una lista de content
    blocks para soportar imágenes (vision):
        [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}]
    """
    role: Literal["system", "user", "assistant", "tool"]
    content: Union[str, List[Dict[str, Any]]]
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ToolFunction:
    """Definición de una function-tool (formato OpenAI function calling)."""
    name: str
    parameters: Dict[str, Any]
    description: Optional[str] = None


@dataclass
class Tool:
    """Wrapper de tool para el formato OpenAI tools."""
    type: Literal["function"] = "function"
    function: Optional[ToolFunction] = None


@dataclass
class FunctionCall:
    """Llamada a función dentro de un tool_call."""
    name: str
    arguments: str  # JSON string


@dataclass
class ToolCall:
    """Tool call generado por el modelo."""
    id: str
    type: Literal["function"]
    function: FunctionCall


@dataclass
class ResponseMessage:
    """Mensaje del assistant en la respuesta."""
    role: Literal["assistant"]
    content: Optional[str]
    tool_calls: Optional[List[ToolCall]] = None
    refusal: Optional[str] = None
    reasoning: Optional[str] = None  # Algunos providers (Groq, DeepSeek) devuelven reasoning textual


@dataclass
class Choice:
    """Una opción de completion."""
    index: int
    message: ResponseMessage
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "function_call"]
    logprobs: Optional[Dict[str, Any]] = None


@dataclass
class Usage:
    """
    Uso de tokens. Soporta extensiones comunes del wire chat/completions.

    Campos estándar OpenAI: prompt_tokens, completion_tokens, total_tokens.
    Extensiones Groq (timing): prompt_time, completion_time, total_time.
    Extensiones reasoning (xAI/Groq/DeepSeek): reasoning_tokens.
    Extensiones caching (varios): cached_tokens.
    """
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_time: Optional[float] = None
    completion_time: Optional[float] = None
    total_time: Optional[float] = None
    reasoning_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None


@dataclass
class ChatCompletionResponse:
    """Respuesta del wire chat/completions, agnóstica al provider."""
    id: str
    object: str  # típicamente "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage
    system_fingerprint: Optional[str] = None
    usage_breakdown: Optional[Dict[str, Any]] = None
