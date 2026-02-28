"""
Modelos de datos para Google Gemini API.

Este módulo contiene todas las clases de datos (dataclasses) utilizadas para
interactuar con la API de Gemini (ai.google.dev), organizadas en tres categorías:
- REQUEST MODELS: Estructuras para construir peticiones
- RESPONSE MODELS: Estructuras para parsear respuestas
- ERROR MODELS: Estructuras para manejar errores

Compatible con:
- Gemini API (generativelanguage.googleapis.com)
- Vertex AI Gemini (aiplatform.googleapis.com)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Literal


# ============================================================================
# REQUEST MODELS
# ============================================================================

@dataclass
class Part:
    """
    Parte de contenido en un mensaje de Gemini.

    Un mensaje puede contener múltiples parts de diferentes tipos.

    Attributes:
        text: Texto del contenido
        inline_data: Datos inline (imagen en base64)
        file_data: Referencia a archivo (URI)
        function_call: Llamada a función generada por el modelo
        function_response: Respuesta a una función (para enviar resultados)
    """
    text: Optional[str] = None
    inline_data: Optional[Dict[str, str]] = None  # {"mimeType": "...", "data": "base64..."}
    file_data: Optional[Dict[str, str]] = None    # {"mimeType": "...", "fileUri": "..."}
    function_call: Optional[Dict[str, Any]] = None  # {"name": "...", "args": {...}}
    function_response: Optional[Dict[str, Any]] = None  # {"name": "...", "response": {...}}
    thought: Optional[bool] = None  # True if this part is a thinking/reasoning part


@dataclass
class Content:
    """
    Mensaje en la conversación.

    Attributes:
        role: Rol del mensaje ("user" o "model")
        parts: Lista de partes del contenido
    """
    role: Literal["user", "model"]
    parts: List[Part]


@dataclass
class FunctionDeclaration:
    """
    Declaración de función disponible para el modelo.

    Attributes:
        name: Nombre único de la función (a-z, A-Z, 0-9, _, .)
        description: Descripción de qué hace la función
        parameters: JSON Schema de los parámetros de entrada
    """
    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class GenerationConfig:
    """
    Configuración para la generación de contenido.

    Attributes:
        temperature: Control de aleatoriedad (0.0-2.0)
        top_p: Nucleus sampling (0.0-1.0)
        top_k: Top-K sampling
        max_output_tokens: Máximo de tokens a generar
        stop_sequences: Secuencias que detienen la generación
        response_mime_type: Formato de respuesta ("text/plain", "application/json")
    """
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    max_output_tokens: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    response_mime_type: Optional[str] = None
    thinking_config: Optional[Dict[str, Any]] = None  # {"thinkingBudget": int}


@dataclass
class SafetySetting:
    """
    Configuración de filtro de seguridad.

    Attributes:
        category: Categoría de daño a filtrar
        threshold: Umbral de bloqueo
    """
    category: Literal[
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_CIVIC_INTEGRITY"
    ]
    threshold: Literal[
        "BLOCK_NONE",
        "BLOCK_ONLY_HIGH",
        "BLOCK_MEDIUM_AND_ABOVE",
        "BLOCK_LOW_AND_ABOVE"
    ]


# ============================================================================
# RESPONSE MODELS
# ============================================================================

@dataclass
class UsageMetadata:
    """
    Estadísticas de uso de tokens.

    Attributes:
        prompt_token_count: Tokens en el prompt
        candidates_token_count: Tokens generados
        total_token_count: Total de tokens
    """
    prompt_token_count: int
    candidates_token_count: int
    total_token_count: int


@dataclass
class SafetyRating:
    """
    Clasificación de seguridad para una categoría.

    Attributes:
        category: Categoría evaluada
        probability: Probabilidad de daño
        blocked: Si fue bloqueado
    """
    category: str
    probability: str
    blocked: bool = False


@dataclass
class Candidate:
    """
    Candidato de respuesta del modelo.

    Attributes:
        content: Contenido generado
        finish_reason: Razón de finalización
        safety_ratings: Clasificaciones de seguridad
    """
    content: Content
    finish_reason: str
    safety_ratings: Optional[List[SafetyRating]] = None


@dataclass
class GeminiResponse:
    """
    Respuesta completa de la API de Gemini.

    Attributes:
        candidates: Lista de respuestas candidatas
        usage_metadata: Estadísticas de tokens
        model_version: Versión del modelo usado
    """
    candidates: List[Candidate]
    usage_metadata: UsageMetadata
    model_version: Optional[str] = None


# ============================================================================
# ERROR MODELS
# ============================================================================

@dataclass
class GeminiError:
    """
    Error devuelto por la API de Gemini.

    Attributes:
        code: Código HTTP del error
        message: Mensaje descriptivo
        status: Estado del error (ej: "INVALID_ARGUMENT")
    """
    code: int
    message: str
    status: str
