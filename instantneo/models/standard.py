"""
Modelos estándar para la interfaz unificada de InstantNeo.

Este módulo define las estructuras de datos que sirven como "contrato"
entre el Core y los Adapters, independientemente del proveedor.

El flujo es:
    Core (usa Standard*) → Adapter (traduce) → Fetcher (HTTP) → API

Los adapters son responsables de:
1. Traducir StandardRequest → formato del proveedor
2. Traducir respuesta del proveedor → StandardResponse
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Literal


# ============================================================================
# CONTENT BLOCKS - Para mensajes multimodales
# ============================================================================

@dataclass
class TextContent:
    """Bloque de contenido de texto."""
    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ImageContent:
    """
    Bloque de contenido de imagen.

    Soporta tres formas de especificar la imagen:
    - url: URL directa a la imagen
    - base64: Datos codificados en base64 (requiere media_type)
    - file_id: ID de archivo en el proveedor (si aplica)
    """
    type: Literal["image"] = "image"
    url: Optional[str] = None
    base64: Optional[str] = None
    media_type: Optional[Literal["image/jpeg", "image/png", "image/gif", "image/webp"]] = None
    detail: Optional[Literal["auto", "low", "high"]] = "auto"
    file_id: Optional[str] = None


# Tipo unión para contenido de mensaje
ContentBlock = Union[TextContent, ImageContent, Dict[str, Any]]


# ============================================================================
# TOOLS - Definición de herramientas/funciones
# ============================================================================

@dataclass
class StandardTool:
    """
    Definición estándar de una herramienta (función).

    Attributes:
        name: Nombre único de la herramienta (regex: ^[a-zA-Z0-9_-]{1,64}$)
        description: Descripción de qué hace la herramienta
        parameters: JSON Schema de los parámetros
    """
    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class StandardToolChoice:
    """
    Control de selección de herramientas.

    Attributes:
        type: Modo de selección
            - "auto": El modelo decide si usar herramientas
            - "none": No usar herramientas
            - "required": Debe usar al menos una herramienta
            - "specific": Forzar una herramienta específica
        name: Nombre de la herramienta (solo para type="specific")
    """
    type: Literal["auto", "none", "required", "specific"] = "auto"
    name: Optional[str] = None


# ============================================================================
# TOOL CALLS - Llamadas a herramientas en respuestas
# ============================================================================

@dataclass
class StandardToolCall:
    """
    Llamada a herramienta generada por el modelo.

    Esta estructura es compatible con lo que el Core espera:
    - tool_call.function.name
    - tool_call.function.arguments (JSON string)

    Attributes:
        id: Identificador único de la llamada
        name: Nombre de la función a invocar
        arguments: Argumentos como JSON string
    """
    id: str
    name: str
    arguments: str  # JSON string para compatibilidad con el core
    type: Literal["function"] = "function"

    @property
    def function(self):
        """
        Propiedad para compatibilidad con el formato esperado por el Core.
        Devuelve un objeto con .name y .arguments
        """
        return _FunctionRef(name=self.name, arguments=self.arguments)


@dataclass
class _FunctionRef:
    """Clase auxiliar para compatibilidad con core.tool_call.function.name"""
    name: str
    arguments: str


# ============================================================================
# MESSAGES - Mensajes de conversación
# ============================================================================

@dataclass
class StandardMessage:
    """
    Mensaje estándar de conversación.

    Attributes:
        role: Rol del emisor
            - "system": Instrucciones del sistema
            - "user": Mensaje del usuario
            - "assistant": Respuesta del modelo
            - "tool": Resultado de una herramienta
        content: Contenido del mensaje (string o lista de ContentBlocks)
        name: Nombre opcional del participante
        tool_call_id: ID de la llamada (solo para role="tool")
        tool_calls: Herramientas invocadas (solo para role="assistant")
    """
    role: Literal["system", "user", "assistant", "tool"]
    content: Union[str, List[ContentBlock]]
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[StandardToolCall]] = None


# ============================================================================
# REQUEST - Petición estándar
# ============================================================================

@dataclass
class StandardRequest:
    """
    Petición estándar para cualquier proveedor.

    Los adapters traducen esta estructura al formato específico del proveedor.

    Attributes:
        model: ID del modelo a usar
        messages: Lista de mensajes de la conversación
        max_tokens: Máximo de tokens a generar (requerido por Anthropic)
        temperature: Control de aleatoriedad (0.0-2.0, Anthropic normaliza a 0-1)
        top_p: Nucleus sampling
        stream: Habilitar streaming
        tools: Herramientas disponibles
        tool_choice: Control de selección de herramientas
        stop: Secuencias de parada
        seed: Semilla para reproducibilidad
        reasoning: Configuración de reasoning/thinking (effort, budget_tokens)
        provider_params: Parámetros específicos del proveedor (passthrough)
    """
    model: str
    messages: List[StandardMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: bool = False
    tools: Optional[List[StandardTool]] = None
    tool_choice: Optional[StandardToolChoice] = None
    stop: Optional[List[str]] = None
    seed: Optional[int] = None
    reasoning: Optional[Dict[str, Any]] = None
    # Parámetros específicos del proveedor pasan sin modificación
    provider_params: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# RESPONSE - Respuesta estándar
# ============================================================================

@dataclass
class StandardUsage:
    """
    Estadísticas de uso de tokens.

    Attributes:
        input_tokens: Tokens en el prompt/entrada
        output_tokens: Tokens generados
        total_tokens: Total de tokens usados
        reasoning_tokens: Tokens usados en reasoning/thinking
    """
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: Optional[int] = None


@dataclass
class StandardChoice:
    """
    Una opción de respuesta (para compatibilidad con formato OpenAI).

    El Core espera response.choices[0].message con .content y .tool_calls
    """
    message: "StandardResponseMessage"
    finish_reason: str
    index: int = 0


@dataclass
class StandardResponseMessage:
    """
    Mensaje en la respuesta del modelo.

    Attributes:
        content: Texto generado (puede ser None si hay tool_calls)
        tool_calls: Herramientas invocadas por el modelo
        reasoning: Contenido de reasoning/thinking del modelo
        role: Siempre "assistant"
    """
    content: Optional[str]
    tool_calls: Optional[List[StandardToolCall]] = None
    reasoning: Optional[str] = None
    role: Literal["assistant"] = "assistant"


@dataclass
class StandardResponse:
    """
    Respuesta estándar de cualquier proveedor.

    Esta estructura es compatible con lo que el Core espera:
    - response.choices[0].message.content
    - response.choices[0].message.tool_calls

    Attributes:
        id: Identificador único de la respuesta
        model: Modelo que generó la respuesta
        choices: Lista de opciones de respuesta
        usage: Estadísticas de tokens
        finish_reason: Razón de finalización
        raw_response: Respuesta original del proveedor (para debugging)
    """
    id: str
    model: str
    choices: List[StandardChoice]
    usage: StandardUsage
    finish_reason: str
    raw_response: Any = None

    # Propiedades de conveniencia
    @property
    def content(self) -> Optional[str]:
        """Atajo para obtener el contenido del primer choice."""
        if self.choices:
            return self.choices[0].message.content
        return None

    @property
    def tool_calls(self) -> Optional[List[StandardToolCall]]:
        """Atajo para obtener las tool_calls del primer choice."""
        if self.choices:
            return self.choices[0].message.tool_calls
        return None


# ============================================================================
# STREAMING - Chunks para respuestas en streaming
# ============================================================================

@dataclass
class StandardStreamDelta:
    """Delta de contenido en streaming."""
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    reasoning: Optional[str] = None
    finish_reason: Optional[str] = None


@dataclass
class StandardStreamChunk:
    """
    Chunk individual de una respuesta en streaming.

    Attributes:
        id: ID de la respuesta
        model: Modelo que genera
        delta: Contenido incremental
        usage: Uso de tokens (solo en último chunk si include_usage=True)
    """
    id: str
    model: str
    delta: StandardStreamDelta
    usage: Optional[StandardUsage] = None


# ============================================================================
# FACTORY HELPERS - Funciones de conveniencia
# ============================================================================

def create_user_message(content: Union[str, List[ContentBlock]]) -> StandardMessage:
    """Crea un mensaje de usuario."""
    return StandardMessage(role="user", content=content)


def create_system_message(content: str) -> StandardMessage:
    """Crea un mensaje de sistema."""
    return StandardMessage(role="system", content=content)


def create_assistant_message(
    content: Optional[str] = None,
    tool_calls: Optional[List[StandardToolCall]] = None
) -> StandardMessage:
    """Crea un mensaje de asistente."""
    return StandardMessage(role="assistant", content=content or "", tool_calls=tool_calls)


def create_tool_result_message(tool_call_id: str, content: str) -> StandardMessage:
    """Crea un mensaje con el resultado de una herramienta."""
    return StandardMessage(role="tool", content=content, tool_call_id=tool_call_id)


def create_tool(name: str, description: str, parameters: Dict[str, Any]) -> StandardTool:
    """Crea una definición de herramienta."""
    return StandardTool(name=name, description=description, parameters=parameters)
