"""
Modelos de datos para Cerebras API.

Este modulo contiene todos los tipos de datos utilizados para interactuar con la API de Cerebras,
incluyendo modelos para requests, responses y errores. Es compatible con el formato de OpenAI
Chat Completions con extensiones especificas de Cerebras.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Literal


# ============================================================================
# REQUEST MODELS - Modelos para construir peticiones a la API
# ============================================================================

@dataclass
class Message:
    """
    Mensaje en la conversacion.

    Representa un mensaje individual en el historial de conversacion,
    que puede ser del sistema, usuario, asistente o una herramienta.

    Attributes:
        role: Rol del emisor del mensaje (system, user, assistant, tool)
        content: Contenido del mensaje. Puede ser un string simple o una lista
            de content blocks para soportar imagenes (vision).
        name: Nombre opcional del participante o funcion
        tool_calls: Lista de llamadas a herramientas (solo para assistant)
        tool_call_id: ID de la llamada a herramienta (solo para role=tool)
    """
    role: Literal["system", "user", "assistant", "tool"]
    content: Union[str, List[Dict[str, Any]]]
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ToolFunction:
    """
    Definicion de una funcion (herramienta).

    Attributes:
        name: Nombre de la funcion
        parameters: Esquema JSON Schema de los parametros de la funcion
        description: Descripcion opcional de lo que hace la funcion
    """
    name: str
    parameters: Dict[str, Any]
    description: Optional[str] = None


@dataclass
class Tool:
    """
    Definicion de herramienta que el modelo puede usar.

    Attributes:
        type: Tipo de herramienta (actualmente solo "function" soportado)
        function: Definicion de la funcion asociada
    """
    type: Literal["function"] = "function"
    function: Optional[ToolFunction] = None


@dataclass
class Prediction:
    """
    Contenido de prediccion para speculative decoding.

    Attributes:
        type: Tipo de prediccion (actualmente solo "content")
        content: Contenido predicho que se espera del modelo
    """
    type: Literal["content"] = "content"
    content: Optional[str] = None


# ============================================================================
# RESPONSE MODELS - Modelos para parsear respuestas de la API
# ============================================================================

@dataclass
class FunctionCall:
    """
    Llamada a funcion dentro de una tool call.

    Attributes:
        name: Nombre de la funcion a invocar
        arguments: Argumentos de la funcion como string JSON
    """
    name: str
    arguments: str  # JSON string


@dataclass
class ToolCall:
    """
    Llamada a herramienta generada por el modelo.

    Attributes:
        id: Identificador unico de esta llamada a herramienta
        type: Tipo de herramienta (actualmente solo "function")
        function: Detalles de la llamada a la funcion
    """
    id: str
    type: Literal["function"]
    function: FunctionCall


@dataclass
class ResponseMessage:
    """
    Mensaje en la respuesta del modelo.

    Attributes:
        role: Siempre "assistant" en las respuestas
        content: Contenido textual generado (puede ser None si hay tool_calls)
        tool_calls: Lista de herramientas que el modelo quiere invocar
        refusal: Mensaje de rechazo si el modelo no puede responder
        reasoning: Contenido de razonamiento (para modelos con clear thinking como gpt-oss-120b)
    """
    role: Literal["assistant"]
    content: Optional[str]
    tool_calls: Optional[List[ToolCall]] = None
    refusal: Optional[str] = None
    reasoning: Optional[str] = None


@dataclass
class Choice:
    """
    Una opcion de completion en la respuesta.

    Attributes:
        index: Indice de esta opcion (0-based)
        message: Mensaje generado por el modelo
        finish_reason: Razon por la que termino la generacion
        logprobs: Probabilidades logaritmicas de los tokens (opcional)
    """
    index: int
    message: ResponseMessage
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"]
    logprobs: Optional[Dict[str, Any]] = None


@dataclass
class PromptTokensDetails:
    """
    Desglose detallado de tokens del prompt.

    Attributes:
        cached_tokens: Numero de tokens servidos desde cache
    """
    cached_tokens: int = 0


@dataclass
class CompletionTokensDetails:
    """
    Desglose detallado de tokens de la completion.

    Attributes:
        accepted_prediction_tokens: Tokens de prediccion aceptados (speculative decoding)
        rejected_prediction_tokens: Tokens de prediccion rechazados (speculative decoding)
    """
    accepted_prediction_tokens: int = 0
    rejected_prediction_tokens: int = 0


@dataclass
class Usage:
    """
    Estadisticas de uso de tokens.

    Attributes:
        prompt_tokens: Tokens usados en el prompt
        completion_tokens: Tokens generados en la completion
        total_tokens: Total de tokens (prompt + completion)
        prompt_tokens_details: Desglose detallado de tokens del prompt
        completion_tokens_details: Desglose detallado de tokens de la completion
    """
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: Optional[PromptTokensDetails] = None
    completion_tokens_details: Optional[CompletionTokensDetails] = None


@dataclass
class TimeInfo:
    """
    Informacion de tiempos de procesamiento de Cerebras.

    Attributes:
        queue_time: Tiempo en cola antes de procesar (segundos)
        prompt_time: Tiempo para procesar el prompt (segundos)
        completion_time: Tiempo para generar la completion (segundos)
        total_time: Tiempo total de procesamiento (segundos)
    """
    queue_time: Optional[float] = None
    prompt_time: Optional[float] = None
    completion_time: Optional[float] = None
    total_time: Optional[float] = None


@dataclass
class CerebrasResponse:
    """
    Respuesta completa de la API de Cerebras.

    Attributes:
        id: Identificador unico de esta completion
        object: Tipo de objeto (siempre "chat.completion")
        created: Timestamp Unix de cuando se creo
        model: Modelo que genero la respuesta
        choices: Lista de opciones de completion generadas
        usage: Estadisticas de uso de tokens
        system_fingerprint: Huella digital del sistema backend
        time_info: Informacion de tiempos de procesamiento
        service_tier_used: Nivel de servicio utilizado
    """
    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: List[Choice]
    usage: Usage
    system_fingerprint: Optional[str] = None
    time_info: Optional[TimeInfo] = None
    service_tier_used: Optional[str] = None


# ============================================================================
# ERROR MODELS - Modelos para manejar errores de la API
# ============================================================================

@dataclass
class CerebrasError:
    """
    Error devuelto por la API de Cerebras.

    Attributes:
        message: Descripcion del error
        type: Tipo de error (ej: "invalid_request_error")
        param: Parametro que causo el error (si aplica)
        code: Codigo de error especifico (si aplica)
    """
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None
