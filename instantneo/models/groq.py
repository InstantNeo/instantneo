"""
Modelos de datos para Groq API.

Este modulo contiene todos los tipos de datos utilizados para interactuar con la API de Groq,
incluyendo modelos para requests, responses y errores. Es compatible con el formato de OpenAI
con extensiones especificas de Groq.
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
        content: Contenido textual del mensaje
        name: Nombre opcional del participante o funcion
        tool_calls: Lista de llamadas a herramientas (solo para assistant)
        tool_call_id: ID de la llamada a herramienta (solo para role=tool)
    """
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ToolFunction:
    """
    Definicion de una funcion (herramienta).

    Especifica los parametros y comportamiento de una funcion que el modelo
    puede invocar durante la generacion de respuestas.

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

    Encapsula una funcion que el modelo puede invocar para obtener
    informacion o realizar acciones.

    Attributes:
        type: Tipo de herramienta (actualmente solo "function" soportado)
        function: Definicion de la funcion asociada
    """
    type: Literal["function"] = "function"
    function: Optional[ToolFunction] = None


@dataclass
class Document:
    """
    Documento para proporcionar contexto adicional.

    Permite pasar documentos o fragmentos de texto que el modelo puede
    usar como contexto para generar respuestas mas informadas.

    Attributes:
        text: Contenido textual del documento
        id: Identificador opcional del documento
    """
    text: str
    id: Optional[str] = None


@dataclass
class SearchSettings:
    """
    Configuracion para busqueda web.

    Controla que dominios incluir o excluir cuando el modelo realiza
    busquedas en la web para complementar su respuesta.

    Attributes:
        exclude_domains: Lista de dominios a excluir de la busqueda
        include_domains: Lista de dominios a incluir en la busqueda
    """
    exclude_domains: Optional[List[str]] = None
    include_domains: Optional[List[str]] = None


# ============================================================================
# RESPONSE MODELS - Modelos para parsear respuestas de la API
# ============================================================================

@dataclass
class FunctionCall:
    """
    Llamada a funcion dentro de una tool call.

    Representa la invocacion especifica de una funcion, incluyendo
    su nombre y argumentos en formato JSON.

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

    Cuando el modelo decide usar una herramienta, genera un objeto ToolCall
    que especifica que funcion invocar y con que parametros.

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

    Representa la respuesta generada por el asistente, que puede incluir
    contenido textual, llamadas a herramientas, o rechazos.

    Attributes:
        role: Siempre "assistant" en las respuestas
        content: Contenido textual generado (puede ser None si hay tool_calls)
        tool_calls: Lista de herramientas que el modelo quiere invocar
        refusal: Mensaje de rechazo si el modelo no puede responder
    """
    role: Literal["assistant"]
    content: Optional[str]
    tool_calls: Optional[List[ToolCall]] = None
    refusal: Optional[str] = None


@dataclass
class Choice:
    """
    Una opcion de completion en la respuesta.

    Cuando se generan multiples completions (parametro n > 1), cada una
    se representa como un Choice separado.

    Attributes:
        index: Indice de esta opcion (0-based)
        message: Mensaje generado por el modelo
        finish_reason: Razon por la que termino la generacion
        logprobs: Probabilidades logaritmicas de los tokens (opcional)
    """
    index: int
    message: ResponseMessage
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "function_call"]
    logprobs: Optional[Dict[str, Any]] = None


@dataclass
class Usage:
    """
    Estadisticas de uso de tokens.

    Proporciona informacion detallada sobre cuantos tokens se utilizaron
    en el prompt y la completion, asi como tiempos de procesamiento.

    Attributes:
        prompt_tokens: Tokens usados en el prompt
        completion_tokens: Tokens generados en la completion
        total_tokens: Total de tokens (prompt + completion)
        prompt_time: Tiempo en segundos para procesar el prompt
        completion_time: Tiempo en segundos para generar la completion
        total_time: Tiempo total de procesamiento
    """
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_time: Optional[float] = None
    completion_time: Optional[float] = None
    total_time: Optional[float] = None


@dataclass
class GroqResponse:
    """
    Respuesta completa de la API de Groq.

    Encapsula toda la informacion devuelta por la API, incluyendo
    las opciones generadas, metadatos y estadisticas de uso.

    Attributes:
        id: Identificador unico de esta completion
        object: Tipo de objeto (siempre "chat.completion")
        created: Timestamp Unix de cuando se creo
        model: Modelo que genero la respuesta
        choices: Lista de opciones de completion generadas
        usage: Estadisticas de uso de tokens
        system_fingerprint: Huella digital del sistema backend
        usage_breakdown: Desglose detallado del uso (opcional)
    """
    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: List[Choice]
    usage: Usage
    system_fingerprint: Optional[str] = None
    usage_breakdown: Optional[Dict[str, Any]] = None


# ============================================================================
# ERROR MODELS - Modelos para manejar errores de la API
# ============================================================================

@dataclass
class GroqError:
    """
    Error devuelto por la API de Groq.

    Cuando la API encuentra un problema, devuelve un objeto de error
    con detalles sobre que salio mal.

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
