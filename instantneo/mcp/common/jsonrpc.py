"""
Utilidades para trabajar con mensajes JSON-RPC.
"""
import json
from typing import Dict, Any, List, Union, Optional, Tuple

# Constantes para códigos de error estándar
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Constantes para códigos de error específicos de MCP
RESOURCE_NOT_FOUND = -32002

class JSONRPCError(Exception):
    """
    Excepción para errores JSON-RPC.
    """
    def __init__(self, code: int, message: str, data: Any = None, id: Any = None):
        self.code = code
        self.message = message
        self.data = data
        self.id = id
        super().__init__(message)
    
    def to_response(self) -> Dict[str, Any]:
        """
        Convierte la excepción a una respuesta JSON-RPC.
        
        Returns:
            Dict: Respuesta JSON-RPC con error
        """
        response = {
            "jsonrpc": "2.0",
            "error": {
                "code": self.code,
                "message": self.message
            },
            "id": self.id
        }
        
        if self.data is not None:
            response["error"]["data"] = self.data
            
        return response

def create_request(method: str, params: Dict[str, Any] = None, id: Union[str, int] = None) -> Dict[str, Any]:
    """
    Crea un objeto de solicitud JSON-RPC.
    
    Args:
        method: Nombre del método a invocar
        params: Parámetros para el método (opcional)
        id: ID de la solicitud (opcional, si no se proporciona es una notificación)
        
    Returns:
        Dict: Objeto de solicitud JSON-RPC
    """
    request = {
        "jsonrpc": "2.0",
        "method": method
    }
    
    if params is not None:
        request["params"] = params
        
    if id is not None:
        request["id"] = id
        
    return request

def create_response(result: Any, id: Union[str, int]) -> Dict[str, Any]:
    """
    Crea un objeto de respuesta JSON-RPC exitosa.
    
    Args:
        result: Resultado de la operación
        id: ID de la solicitud original
        
    Returns:
        Dict: Objeto de respuesta JSON-RPC
    """
    return {
        "jsonrpc": "2.0",
        "result": result,
        "id": id
    }

def create_error_response(code: int, message: str, id: Union[str, int, None], data: Any = None) -> Dict[str, Any]:
    """
    Crea un objeto de respuesta JSON-RPC con error.
    
    Args:
        code: Código de error
        message: Mensaje de error
        id: ID de la solicitud original (puede ser None)
        data: Datos adicionales del error (opcional)
        
    Returns:
        Dict: Objeto de respuesta JSON-RPC con error
    """
    response = {
        "jsonrpc": "2.0",
        "error": {
            "code": code,
            "message": message
        },
        "id": id
    }
    
    if data is not None:
        response["error"]["data"] = data
        
    return response

def create_notification(method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Crea un objeto de notificación JSON-RPC.
    
    Args:
        method: Nombre del método a invocar
        params: Parámetros para el método (opcional)
        
    Returns:
        Dict: Objeto de notificación JSON-RPC
    """
    return create_request(method, params)

def parse_message(message_str: str) -> Tuple[Union[Dict[str, Any], List[Dict[str, Any]]], Optional[JSONRPCError]]:
    """
    Parsea un mensaje JSON-RPC desde un string.
    
    Args:
        message_str: Mensaje JSON-RPC como string
        
    Returns:
        Tuple: (mensaje parseado, error) - si hay error, el mensaje será None
    """
    try:
        message = json.loads(message_str)
        return message, None
    except json.JSONDecodeError:
        error = JSONRPCError(
            code=PARSE_ERROR,
            message="Parse error",
            id=None
        )
        return None, error

def is_request(message: Dict[str, Any]) -> bool:
    """
    Verifica si un mensaje es una solicitud JSON-RPC.
    
    Args:
        message: Mensaje JSON-RPC
        
    Returns:
        bool: True si es una solicitud, False en caso contrario
    """
    return (
        isinstance(message, dict) and
        message.get("jsonrpc") == "2.0" and
        "method" in message and
        "id" in message
    )

def is_notification(message: Dict[str, Any]) -> bool:
    """
    Verifica si un mensaje es una notificación JSON-RPC.
    
    Args:
        message: Mensaje JSON-RPC
        
    Returns:
        bool: True si es una notificación, False en caso contrario
    """
    return (
        isinstance(message, dict) and
        message.get("jsonrpc") == "2.0" and
        "method" in message and
        "id" not in message
    )

def is_response(message: Dict[str, Any]) -> bool:
    """
    Verifica si un mensaje es una respuesta JSON-RPC.
    
    Args:
        message: Mensaje JSON-RPC
        
    Returns:
        bool: True si es una respuesta, False en caso contrario
    """
    return (
        isinstance(message, dict) and
        message.get("jsonrpc") == "2.0" and
        "id" in message and
        ("result" in message or "error" in message)
    )

def is_batch(message: Any) -> bool:
    """
    Verifica si un mensaje es un batch JSON-RPC.
    
    Args:
        message: Mensaje JSON-RPC
        
    Returns:
        bool: True si es un batch, False en caso contrario
    """
    return isinstance(message, list) and len(message) > 0