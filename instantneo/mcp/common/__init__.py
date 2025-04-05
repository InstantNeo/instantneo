"""
Módulo común para componentes compartidos entre cliente y servidor MCP.

Este módulo exporta las clases y funciones principales para uso compartido
en las implementaciones de cliente y servidor del Model Context Protocol.
"""

# En las primeras etapas de desarrollo, usamos importaciones relativas
# A medida que agreguemos más módulos, iremos actualizando estas importaciones

# Importaciones de configuración
from .config import get_default_config, merge_configs

# Importaciones de utilidades JSON-RPC
from .jsonrpc import (
    create_request,
    create_response,
    create_error_response,
    create_notification,
    parse_message
)

# Importaciones de utilidades SSL
from .ssl_tools import generate_self_signed_cert, validate_certificate

# Definición de constantes del protocolo MCP
MCP_PROTOCOL_VERSION = "2025-03-26"
JSONRPC_VERSION = "2.0"

# Códigos de error estándar JSON-RPC
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Códigos de error personalizados MCP
AUTH_ERROR = -32000
RATE_LIMIT_ERROR = -32001
RESOURCE_NOT_FOUND = -32002

__all__ = [
    # Constantes
    'MCP_PROTOCOL_VERSION',
    'JSONRPC_VERSION',
    # Códigos de error
    'PARSE_ERROR',
    'INVALID_REQUEST',
    'METHOD_NOT_FOUND',
    'INVALID_PARAMS',
    'INTERNAL_ERROR',
    'AUTH_ERROR',
    'RATE_LIMIT_ERROR',
    'RESOURCE_NOT_FOUND',
    # Funciones de configuración
    'get_default_config',
    'merge_configs',
    # Funciones JSON-RPC
    'create_request',
    'create_response',
    'create_error_response',
    'create_notification',
    'parse_message',
    # Funciones SSL
    'generate_self_signed_cert',
    'validate_certificate',
]