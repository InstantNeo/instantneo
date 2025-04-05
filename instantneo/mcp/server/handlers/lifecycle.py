"""
Manejadores para operaciones del ciclo de vida MCP.
"""
import logging
from typing import Dict, Any, Optional

from ...common.jsonrpc import create_response, create_error_response

logger = logging.getLogger("mcp_server.handlers.lifecycle")

def handle_initialize(server, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """
    Maneja la solicitud initialize.
    
    Args:
        server: Instancia del servidor MCP
        params: Parámetros de la solicitud
        request_id: ID de la solicitud
        
    Returns:
        Dict: Respuesta JSON-RPC
    """
    try:
        # Extraer información del cliente
        client_protocol_version = params.get("protocolVersion")
        client_capabilities = params.get("capabilities", {})
        client_info = params.get("clientInfo", {})

        # Registrar sesión
        session_id = f"session_{len(server.sessions) + 1}"
        server.sessions[session_id] = {
            "id": session_id,
            "client_info": client_info,
            "client_capabilities": client_capabilities,
            "protocol_version": client_protocol_version,
            "created_at": server._get_current_time(),
            "expires_at": server._get_current_time() + server.config.get("session_timeout", 3600)
        }

        # ✨ ESTA ES LA RESPUESTA SIMPLE Y VÁLIDA PARA CLAUDE:
        result = {
            "serverInfo": {
                "name": server.config.get("server_name", "InstantNeo MCP Server"),
                "version": server.config.get("server_version", "1.0.0")
            },
            "capabilities": {
                "tools": True  # Claude requiere que esto sea un booleano, no un dict
            }
        }

        logger.info(f"Cliente inicializado: {client_info.get('name', 'desconocido')} {client_info.get('version', '')}")
        return create_response(result, request_id)

    except Exception as e:
        logger.exception("Error en inicialización")
        return create_error_response(-32603, f"Error interno: {str(e)}", request_id)

def handle_initialized(server, params: Dict[str, Any]) -> None:
    """
    Maneja la notificación initialized.
    
    Args:
        server: Instancia del servidor MCP
        params: Parámetros de la notificación
    """
    logger.info("Cliente completó inicialización")
    # No se requiere respuesta para notificaciones

def handle_ping(request_id: Any) -> Dict[str, Any]:
    """
    Maneja la solicitud ping.
    
    Args:
        request_id: ID de la solicitud
        
    Returns:
        Dict: Respuesta JSON-RPC
    """
    # Simplemente devolver un objeto vacío como resultado
    return create_response({}, request_id)

def handle_cancelled(server, params: Dict[str, Any]) -> None:
    """
    Maneja la notificación cancelled.
    
    Args:
        server: Instancia del servidor MCP
        params: Parámetros de la notificación
    """
    request_id = params.get("requestId")
    reason = params.get("reason", "No reason provided")
    
    logger.info(f"Solicitud cancelada: {request_id}, razón: {reason}")
    # No se requiere respuesta para notificaciones