"""
Manejadores centralizados para errores MCP.
"""
import logging
import traceback
from typing import Dict, Any, Optional, Union

from ...common.jsonrpc import (
    create_error_response,
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR
)

logger = logging.getLogger("mcp_server.handlers.errors")

def handle_parse_error(error: Exception, request_id: Optional[Union[str, int]] = None) -> Dict[str, Any]:
    """
    Maneja errores de parseo JSON.
    
    Args:
        error: Excepción de parseo
        request_id: ID de la solicitud (si se conoce)
        
    Returns:
        Dict: Respuesta JSON-RPC con error
    """
    logger.error(f"Error de parseo JSON: {str(error)}")
    return create_error_response(
        PARSE_ERROR,
        "Parse error",
        request_id
    )

def handle_invalid_request(error_message: str, request_id: Optional[Union[str, int]] = None) -> Dict[str, Any]:
    """
    Maneja solicitudes JSON-RPC inválidas.
    
    Args:
        error_message: Mensaje de error
        request_id: ID de la solicitud (si se conoce)
        
    Returns:
        Dict: Respuesta JSON-RPC con error
    """
    logger.error(f"Solicitud inválida: {error_message}")
    return create_error_response(
        INVALID_REQUEST,
        f"Invalid Request: {error_message}",
        request_id
    )

def handle_method_not_found(method: str, request_id: Union[str, int]) -> Dict[str, Any]:
    """
    Maneja errores de método no encontrado.
    
    Args:
        method: Nombre del método solicitado
        request_id: ID de la solicitud
        
    Returns:
        Dict: Respuesta JSON-RPC con error
    """
    logger.warning(f"Método no encontrado: {method}")
    return create_error_response(
        METHOD_NOT_FOUND,
        f"Method not found: {method}",
        request_id
    )

def handle_invalid_params(error_message: str, request_id: Union[str, int]) -> Dict[str, Any]:
    """
    Maneja errores de parámetros inválidos.
    
    Args:
        error_message: Mensaje de error
        request_id: ID de la solicitud
        
    Returns:
        Dict: Respuesta JSON-RPC con error
    """
    logger.warning(f"Parámetros inválidos: {error_message}")
    return create_error_response(
        INVALID_PARAMS,
        f"Invalid params: {error_message}",
        request_id
    )

def handle_internal_error(error: Exception, request_id: Union[str, int]) -> Dict[str, Any]:
    """
    Maneja errores internos del servidor.
    
    Args:
        error: Excepción ocurrida
        request_id: ID de la solicitud
        
    Returns:
        Dict: Respuesta JSON-RPC con error
    """
    error_traceback = traceback.format_exc()
    logger.error(f"Error interno: {str(error)}\n{error_traceback}")
    
    # En producción, no exponer detalles del error
    return create_error_response(
        INTERNAL_ERROR,
        "Internal error",
        request_id,
        # Incluir detalles solo en entornos de desarrollo
        data=str(error) if logger.level <= logging.DEBUG else None
    )

def handle_unauthorized(request_id: Union[str, int]) -> Dict[str, Any]:
    """
    Maneja errores de autorización.
    
    Args:
        request_id: ID de la solicitud
        
    Returns:
        Dict: Respuesta JSON-RPC con error
    """
    logger.warning("Acceso no autorizado")
    return create_error_response(
        -32001,  # Código personalizado para no autorizado
        "Unauthorized",
        request_id
    )

def handle_resource_not_found(resource_uri: str, request_id: Union[str, int]) -> Dict[str, Any]:
    """
    Maneja errores de recurso no encontrado.
    
    Args:
        resource_uri: URI del recurso solicitado
        request_id: ID de la solicitud
        
    Returns:
        Dict: Respuesta JSON-RPC con error
    """
    logger.warning(f"Recurso no encontrado: {resource_uri}")
    return create_error_response(
        -32002,  # Código para recurso no encontrado
        "Resource not found",
        request_id,
        data={"uri": resource_uri}
    )