"""
Manejadores para operaciones relacionadas con tools MCP.
"""
import json
import logging
from typing import Dict, Any, List, Optional

from ...common.jsonrpc import create_response, create_error_response, METHOD_NOT_FOUND, INVALID_PARAMS
from ...common.converters import mcp_tool_result_to_response

logger = logging.getLogger("mcp_server.handlers.tools")

def handle_list_tools(server, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """
    Maneja la solicitud tools/list.
    
    Args:
        server: Instancia del servidor MCP
        params: Parámetros de la solicitud
        request_id: ID de la solicitud
        
    Returns:
        Dict: Respuesta JSON-RPC
    """
    try:
        # Obtener herramientas del servidor
        tools = server.get_tools()
        
        # Manejar paginación si se proporciona un cursor
        cursor = params.get("cursor")
        page_size = server.config.get("pagination", {}).get("page_size", 100)
        
        if cursor:
            try:
                # Decodificar cursor (formato simple: índice)
                start_index = int(cursor)
            except (ValueError, TypeError):
                start_index = 0
        else:
            start_index = 0
        
        # Calcular fin de página y siguiente cursor
        end_index = min(start_index + page_size, len(tools))
        next_cursor = str(end_index) if end_index < len(tools) else None
        
        # Obtener herramientas para esta página
        page_tools = tools[start_index:end_index]
        
        # Construir respuesta
        result = {
            "tools": page_tools
        }
        
        if next_cursor:
            result["nextCursor"] = next_cursor
        
        return create_response(result, request_id)
    
    except Exception as e:
        logger.exception("Error al listar tools")
        return create_error_response(-32603, f"Error interno: {str(e)}", request_id)

def handle_call_tool(server, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """
    Maneja la solicitud tools/call.
    
    Args:
        server: Instancia del servidor MCP
        params: Parámetros de la solicitud
        request_id: ID de la solicitud
        
    Returns:
        Dict: Respuesta JSON-RPC
    """
    try:
        # Extraer nombre de la herramienta y argumentos
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            return create_error_response(
                INVALID_PARAMS,
                "Falta el parámetro 'name'",
                request_id
            )
        
        # Verificar si la herramienta existe
        skill_names = server.skill_manager.get_skill_names()
        if tool_name not in skill_names:
            return create_error_response(
                METHOD_NOT_FOUND,
                f"Tool no encontrada: {tool_name}",
                request_id
            )
        
        # Ejecutar la herramienta
        result = server.execute_tool(tool_name, arguments)
        
        # Convertir resultado a formato MCP
        mcp_result = mcp_tool_result_to_response(result)
        
        return create_response(mcp_result, request_id)
    
    except Exception as e:
        logger.exception(f"Error al ejecutar tool {params.get('name', 'desconocida')}")
        
        # Devolver error como resultado de la herramienta, no como error JSON-RPC
        error_result = {
            "content": [
                {
                    "type": "text",
                    "text": f"Error al ejecutar la herramienta: {str(e)}"
                }
            ],
            "isError": True
        }
        
        return create_response(error_result, request_id)