"""
Modelos de datos para Anthropic Claude API.

Este módulo contiene todas las clases de datos (dataclasses) utilizadas para
interactuar con la API de Anthropic Claude, organizadas en tres categorías:
- REQUEST MODELS: Estructuras para construir peticiones
- RESPONSE MODELS: Estructuras para parsear respuestas
- ERROR MODELS: Estructuras para manejar errores
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Literal


# ============================================================================
# REQUEST MODELS
# ============================================================================

@dataclass
class MessageContent:
    """
    Contenido de un mensaje (puede ser texto, imagen, documento, etc.).

    Attributes:
        type: Tipo de contenido (ej: "text", "image", "document")
        text: Texto del mensaje (opcional, usado cuando type="text")
        source: Fuente del contenido para imágenes/documentos (opcional)
    """
    type: str
    text: Optional[str] = None
    source: Optional[Dict[str, Any]] = None


@dataclass
class Message:
    """
    Mensaje en la conversación entre usuario y asistente.

    Attributes:
        role: Rol del mensaje ("user" o "assistant")
        content: Contenido del mensaje (string simple o lista de bloques estructurados)
    """
    role: Literal["user", "assistant"]
    content: Union[str, List[Dict[str, Any]]]


@dataclass
class Tool:
    """
    Definición de herramienta (función) que el modelo puede usar.

    Las herramientas permiten al modelo invocar funciones externas durante
    la generación de respuestas.

    Attributes:
        name: Nombre identificador de la herramienta
        input_schema: Esquema JSON que define los parámetros de entrada
        description: Descripción de qué hace la herramienta (opcional)
    """
    name: str
    input_schema: Dict[str, Any]
    description: Optional[str] = None


@dataclass
class CacheControl:
    """
    Control de caché para bloques de contenido.

    Permite configurar el comportamiento de caché efímero para optimizar
    el uso de tokens en conversaciones largas.

    Attributes:
        type: Tipo de caché (por defecto "ephemeral")
        ttl: Tiempo de vida del caché (por defecto "5m" - 5 minutos)
    """
    type: Literal["ephemeral"] = "ephemeral"
    ttl: Literal["5m", "1h"] = "5m"


# ============================================================================
# RESPONSE MODELS
# ============================================================================

@dataclass
class ContentBlock:
    """
    Bloque de contenido en la respuesta del modelo.

    Un mensaje puede contener múltiples bloques de contenido de diferentes tipos
    (texto, pensamiento, invocación de herramienta, etc.).

    Attributes:
        type: Tipo de bloque (ej: "text", "thinking", "tool_use")
        text: Texto del bloque (para bloques de tipo "text")
        thinking: Contenido de pensamiento extendido (para bloques "thinking")
        id: Identificador único del bloque (para tool_use)
        name: Nombre de la herramienta invocada (para tool_use)
        input: Parámetros de entrada de la herramienta (para tool_use)
    """
    type: str
    text: Optional[str] = None
    thinking: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[Dict[str, Any]] = None


@dataclass
class Usage:
    """
    Estadísticas de uso de tokens en la respuesta.

    Proporciona información detallada sobre el consumo de tokens,
    incluyendo métricas de caché para optimización de costos.

    Attributes:
        input_tokens: Tokens consumidos en la entrada
        output_tokens: Tokens generados en la salida
        cache_creation_input_tokens: Tokens usados para crear caché (opcional)
        cache_read_input_tokens: Tokens leídos desde caché (opcional)
    """
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None


@dataclass
class AnthropicResponse:
    """
    Respuesta completa de la API de Anthropic.

    Esta es la estructura principal que contiene toda la información
    devuelta por el endpoint /v1/messages.

    Attributes:
        id: Identificador único de la respuesta
        type: Tipo de respuesta (normalmente "message")
        role: Rol de la respuesta (normalmente "assistant")
        content: Lista de bloques de contenido en la respuesta
        model: Modelo que generó la respuesta
        stop_reason: Razón por la que se detuvo la generación (ej: "end_turn", "max_tokens")
        stop_sequence: Secuencia de parada que activó el fin (si aplica)
        usage: Estadísticas de uso de tokens
        context_management: Configuración de gestión de contexto (opcional)
        container: Información del contenedor (opcional)
    """
    id: str
    type: str
    role: str
    content: List[ContentBlock]
    model: str
    stop_reason: Optional[str]
    stop_sequence: Optional[str]
    usage: Usage

    # Campos opcionales adicionales
    context_management: Optional[Dict[str, Any]] = None
    container: Optional[Dict[str, Any]] = None


# ============================================================================
# ERROR MODELS
# ============================================================================

@dataclass
class AnthropicError:
    """
    Error devuelto por la API de Anthropic.

    Estructura que encapsula los errores HTTP retornados por la API,
    proporcionando información sobre qué salió mal.

    Attributes:
        type: Tipo de error (ej: "invalid_request_error", "authentication_error")
        message: Mensaje descriptivo del error
    """
    type: str
    message: str
