"""
Modelos de datos para OpenAI API.

Este módulo contiene todas las estructuras de datos utilizadas para
interactuar con la API de OpenAI, incluyendo:
- Modelos de entrada (request)
- Modelos de salida (response)
- Modelos de error y configuración
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Literal


# ============================================================================
# REQUEST MODELS - INPUT CONTENT
# ============================================================================

@dataclass
class InputText:
    """Contenido de texto de entrada"""
    type: Literal["input_text"] = "input_text"
    text: Optional[str] = None


@dataclass
class InputImage:
    """Contenido de imagen de entrada"""
    type: Literal["input_image"] = "input_image"
    detail: Optional[Literal["high", "low", "auto"]] = "auto"
    file_id: Optional[str] = None
    image_url: Optional[str] = None


@dataclass
class InputFile:
    """Contenido de archivo de entrada"""
    type: Literal["input_file"] = "input_file"
    file_data: Optional[str] = None
    file_id: Optional[str] = None
    file_url: Optional[str] = None
    filename: Optional[str] = None


@dataclass
class InputAudioData:
    """Datos de audio de entrada"""
    data: str
    format: Literal["mp3", "wav"]


@dataclass
class InputAudio:
    """Contenido de audio de entrada"""
    type: Literal["input_audio"] = "input_audio"
    input_audio: Optional[InputAudioData] = None


@dataclass
class InputMessage:
    """Mensaje de entrada al modelo"""
    role: Literal["user", "assistant", "system", "developer"]
    content: Union[str, List[Union[InputText, InputImage, InputFile, InputAudio, Dict[str, Any]]]]
    type: Literal["message"] = "message"


# ============================================================================
# REQUEST MODELS - TOOLS
# ============================================================================

@dataclass
class FunctionTool:
    """Definición de herramienta de función personalizada"""
    name: str
    parameters: Dict[str, Any]
    type: Literal["function"] = "function"
    strict: bool = True
    description: Optional[str] = None


@dataclass
class FileSearchTool:
    """Herramienta de búsqueda de archivos"""
    vector_store_ids: List[str]
    type: Literal["file_search"] = "file_search"
    filters: Optional[Dict[str, Any]] = None


@dataclass
class WebSearchTool:
    """Herramienta de búsqueda web"""
    type: Literal["web_search_preview"] = "web_search_preview"


@dataclass
class CodeInterpreterTool:
    """Herramienta de intérprete de código"""
    type: Literal["code_interpreter"] = "code_interpreter"


@dataclass
class ComputerUseTool:
    """Herramienta de uso de computadora"""
    type: Literal["computer_use_preview"] = "computer_use_preview"


@dataclass
class ImageGenerationTool:
    """Herramienta de generación de imágenes"""
    type: Literal["image_generation"] = "image_generation"


# ============================================================================
# REQUEST MODELS - TEXT FORMATS
# ============================================================================

@dataclass
class TextFormat:
    """Formato de texto plano"""
    type: Literal["text"] = "text"


@dataclass
class JsonSchemaFormat:
    """Formato de esquema JSON"""
    name: str
    schema: Dict[str, Any]
    type: Literal["json_schema"] = "json_schema"
    description: Optional[str] = None
    strict: bool = False


@dataclass
class JsonObjectFormat:
    """Formato de objeto JSON (método antiguo)"""
    type: Literal["json_object"] = "json_object"


# ============================================================================
# REQUEST MODELS - CONFIGURATION
# ============================================================================

@dataclass
class TextConfig:
    """Configuración de respuesta de texto"""
    format: Optional[Union[TextFormat, JsonSchemaFormat, JsonObjectFormat]] = None
    verbosity: Optional[Literal["low", "medium", "high"]] = "medium"


@dataclass
class ReasoningConfig:
    """Configuración de razonamiento (solo modelos gpt-5 y serie-o)"""
    effort: Optional[Literal["minimal", "low", "medium", "high"]] = "medium"
    summary: Optional[Literal["auto", "concise", "detailed"]] = None


@dataclass
class StreamOptions:
    """Opciones para respuestas en streaming"""
    include_obfuscation: Optional[bool] = None


@dataclass
class PromptReference:
    """Referencia a una plantilla de prompt"""
    id: str
    variables: Optional[Dict[str, Any]] = None
    version: Optional[str] = None


@dataclass
class Conversation:
    """Conversación a la que pertenece la respuesta"""
    id: str


# ============================================================================
# RESPONSE MODELS - OUTPUT CONTENT
# ============================================================================

@dataclass
class OutputText:
    """Contenido de texto generado por el modelo"""
    text: str
    type: Literal["output_text"] = "output_text"
    annotations: Optional[List[Dict[str, Any]]] = None
    logprobs: Optional[Dict[str, Any]] = None


@dataclass
class ToolCall:
    """Llamada a herramienta realizada por el modelo"""
    type: str  # function, file_search, web_search_preview, code_interpreter, computer_use_preview, image_generation
    id: str
    name: Optional[str] = None
    arguments: Optional[str] = None


@dataclass
class Reasoning:
    """Razonamiento interno del modelo (solo modelos de razonamiento)"""
    type: Literal["reasoning"] = "reasoning"
    summary: Optional[str] = None
    content: Optional[str] = None
    encrypted_content: Optional[str] = None


@dataclass
class OutputMessage:
    """Mensaje de salida generado por el modelo"""
    content: List[Union[OutputText, Dict[str, Any]]]
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    status: Optional[Literal["in_progress", "completed", "incomplete"]] = None


# ============================================================================
# RESPONSE MODELS - USAGE & DETAILS
# ============================================================================

@dataclass
class UsageDetails:
    """Detalles de uso de tokens"""
    audio_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    text_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None


@dataclass
class Usage:
    """Estadísticas de uso de tokens"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: Optional[UsageDetails] = None
    completion_tokens_details: Optional[UsageDetails] = None


@dataclass
class IncompleteDetails:
    """Detalles sobre por qué la respuesta está incompleta"""
    reason: Literal["max_output_tokens", "max_completion_tokens", "content_filter", "tool_calls", "stop_sequence"]


# ============================================================================
# ERROR MODELS
# ============================================================================

@dataclass
class ErrorDetails:
    """Error devuelto por la API"""
    code: str
    message: str


# ============================================================================
# RESPONSE MODELS - MAIN RESPONSE
# ============================================================================

@dataclass
class OpenAIResponse:
    """Respuesta completa de la API de OpenAI"""
    id: str
    model: str
    created_at: int
    status: Literal["completed", "failed", "in_progress", "cancelled", "queued", "incomplete"]
    object: Literal["response"] = "response"

    # Campos opcionales
    output: Optional[List[Union[OutputMessage, ToolCall, Reasoning, Dict[str, Any]]]] = None
    output_text: Optional[str] = None
    usage: Optional[Usage] = None
    incomplete_details: Optional[IncompleteDetails] = None
    error: Optional[ErrorDetails] = None

    # Configuración de la request
    background: Optional[bool] = None
    conversation: Optional[Conversation] = None
    instructions: Optional[Union[str, List[InputMessage]]] = None
    max_output_tokens: Optional[int] = None
    max_tool_calls: Optional[int] = None
    metadata: Optional[Dict[str, str]] = None
    parallel_tool_calls: Optional[bool] = None
    previous_response_id: Optional[str] = None
    prompt: Optional[PromptReference] = None
    prompt_cache_key: Optional[str] = None
    reasoning: Optional[ReasoningConfig] = None
    safety_identifier: Optional[str] = None
    service_tier: Optional[Literal["auto", "default", "flex", "priority"]] = None
    temperature: Optional[float] = None
    text: Optional[TextConfig] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    tools: Optional[List[Union[FunctionTool, FileSearchTool, WebSearchTool, CodeInterpreterTool, ComputerUseTool, ImageGenerationTool, Dict[str, Any]]]] = None
    top_logprobs: Optional[int] = None
    top_p: Optional[float] = None
    truncation: Optional[Dict[str, Any]] = None
