"""
Modelos de datos para Groq API.

Los tipos del formato wire chat/completions (Message, Tool, ToolCall, etc.)
viven ahora en `instantneo.fetchers._chat_completions` para ser compartidos
entre Groq, xAI, Mistral, DeepSeek y otros providers OpenAI-compat. Este
módulo los re-exporta para mantener compatibilidad de imports existentes,
y añade los tipos Groq-específicos (Document, SearchSettings, GroqError).
"""

from dataclasses import dataclass
from typing import List, Optional

# Re-exports desde la base chat/completions — mantienen compat con código
# que importa `from instantneo.models.groq import Message, Tool, ...`.
from instantneo.models._chat_completions import (  # noqa: F401
    Message,
    Tool,
    ToolFunction,
    FunctionCall,
    ToolCall,
    ResponseMessage,
    Choice,
    Usage,
    ChatCompletionResponse as GroqResponse,
)


# ============================================================================
# TIPOS GROQ-ESPECÍFICOS (no parte del wire chat/completions estándar)
# ============================================================================

@dataclass
class Document:
    """
    Documento para proporcionar contexto adicional (extensión Groq).

    Attributes:
        text: Contenido textual del documento.
        id: Identificador opcional del documento.
    """
    text: str
    id: Optional[str] = None


@dataclass
class SearchSettings:
    """
    Configuración para búsqueda web (extensión Groq).

    Attributes:
        exclude_domains: Lista de dominios a excluir de la búsqueda.
        include_domains: Lista de dominios a incluir en la búsqueda.
    """
    exclude_domains: Optional[List[str]] = None
    include_domains: Optional[List[str]] = None


@dataclass
class GroqError:
    """Error devuelto por la API de Groq."""
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None
