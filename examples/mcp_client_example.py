"""
Cliente MCP de ejemplo para probar la comunicación con el servidor MCP.

Este ejemplo muestra cómo conectarse a un servidor MCP, inicializar la conexión,
listar las tools disponibles y llamar a una tool.

Para ejecutar este ejemplo:
1. Primero inicia el servidor MCP con: python examples/mcp_server_example.py
2. Luego ejecuta este cliente: python examples/mcp_client_example.py
"""

import json
import requests
import sys
import time
import uuid

# URL del servidor MCP
SERVER_URL = "http://localhost:8000/mcp"

def create_jsonrpc_request(method, params=None, request_id=None):
    """
    Crea una solicitud JSON-RPC.
    
    Args:
        method: Nombre del método a invocar
        params: Parámetros para el método (opcional)
        request_id: ID de la solicitud (opcional, se genera uno si no se proporciona)
        
    Returns:
        dict: Objeto de solicitud JSON-RPC
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
        
    request = {
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id
    }
    
    if params is not None:
        request["params"] = params
        
    return request

def send_jsonrpc_request(url, method, params=None, request_id=None):
    """
    Envía una solicitud JSON-RPC al servidor.
    
    Args:
        url: URL del servidor MCP
        method: Nombre del método a invocar
        params: Parámetros para el método (opcional)
        request_id: ID de la solicitud (opcional)
        
    Returns:
        dict: Respuesta JSON-RPC
    """
    request = create_jsonrpc_request(method, params, request_id)
    
    try:
        response = requests.post(url, json=request)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error HTTP: {response.status_code}")
            print(f"Respuesta: {response.text}")
            return None
    except Exception as e:
        print(f"Error al enviar solicitud: {e}")
        return None

def send_jsonrpc_notification(url, method, params=None):
    """
    Envía una notificación JSON-RPC al servidor.
    
    Args:
        url: URL del servidor MCP
        method: Nombre del método a invocar
        params: Parámetros para el método (opcional)
        
    Returns:
        bool: True si se envió correctamente, False en caso contrario
    """
    notification = {
        "jsonrpc": "2.0",
        "method": method
    }
    
    if params is not None:
        notification["params"] = params
        
    try:
        response = requests.post(url, json=notification)
        
        return response.status_code == 202  # Accepted
    except Exception as e:
        print(f"Error al enviar notificación: {e}")
        return False

def initialize_connection(url):
    """
    Inicializa la conexión con el servidor MCP.
    
    Args:
        url: URL del servidor MCP
        
    Returns:
        dict: Respuesta de inicialización
    """
    params = {
        "protocolVersion": "2025-03-26",
        "capabilities": {
            "sampling": {}
        },
        "clientInfo": {
            "name": "InstantNeo MCP Client Example",
            "version": "1.0.0"
        }
    }
    
    print("Inicializando conexión con el servidor MCP...")
    response = send_jsonrpc_request(url, "initialize", params)
    
    if response:
        print("Conexión inicializada correctamente")
        print(f"Versión del protocolo: {response['result']['protocolVersion']}")
        print(f"Información del servidor: {response['result']['serverInfo']['name']} {response['result']['serverInfo']['version']}")
        
        # Enviar notificación initialized
        if send_jsonrpc_notification(url, "notifications/initialized"):
            print("Notificación initialized enviada correctamente")
        else:
            print("Error al enviar notificación initialized")
    else:
        print("Error al inicializar conexión")
        sys.exit(1)
        
    return response

def list_tools(url):
    """
    Lista las tools disponibles en el servidor MCP.
    
    Args:
        url: URL del servidor MCP
        
    Returns:
        list: Lista de tools
    """
    print("\nListando tools disponibles...")
    response = send_jsonrpc_request(url, "tools/list")
    
    if response and "result" in response and "tools" in response["result"]:
        tools = response["result"]["tools"]
        print(f"Se encontraron {len(tools)} tools:")
        
        for i, tool in enumerate(tools, 1):
            print(f"{i}. {tool['name']}: {tool['description']}")
            
            # Mostrar parámetros
            if "inputSchema" in tool and "properties" in tool["inputSchema"]:
                print("   Parámetros:")
                for param_name, param_info in tool["inputSchema"]["properties"].items():
                    required = "Requerido" if "required" in tool["inputSchema"] and param_name in tool["inputSchema"]["required"] else "Opcional"
                    param_type = param_info.get("type", "any")
                    description = param_info.get("description", "")
                    print(f"   - {param_name} ({param_type}, {required}): {description}")
            
            print()
            
        return tools
    else:
        print("Error al listar tools")
        return []

def call_tool(url, tool_name, arguments):
    """
    Llama a una tool en el servidor MCP.
    
    Args:
        url: URL del servidor MCP
        tool_name: Nombre de la tool a llamar
        arguments: Argumentos para la tool
        
    Returns:
        dict: Resultado de la llamada
    """
    params = {
        "name": tool_name,
        "arguments": arguments
    }
    
    print(f"\nLlamando a tool '{tool_name}' con argumentos: {json.dumps(arguments)}")
    response = send_jsonrpc_request(url, "tools/call", params)
    
    if response and "result" in response:
        result = response["result"]
        
        if "isError" in result and result["isError"]:
            print("La llamada a la tool resultó en un error:")
        else:
            print("Resultado de la llamada a la tool:")
            
        if "content" in result:
            for content_item in result["content"]:
                if content_item["type"] == "text":
                    print(f"  {content_item['text']}")
                else:
                    print(f"  Contenido de tipo {content_item['type']}")
        
        return result
    else:
        print("Error al llamar a la tool")
        return None

def ping_server(url):
    """
    Envía un ping al servidor MCP.
    
    Args:
        url: URL del servidor MCP
        
    Returns:
        bool: True si el servidor respondió correctamente, False en caso contrario
    """
    print("\nEnviando ping al servidor...")
    response = send_jsonrpc_request(url, "ping")
    
    if response:
        print("Servidor respondió correctamente al ping")
        return True
    else:
        print("Error al enviar ping")
        return False

def main():
    """Función principal."""
    print("Cliente MCP de ejemplo")
    print("=====================")
    
    # Inicializar conexión
    initialize_connection(SERVER_URL)
    
    # Listar tools
    tools = list_tools(SERVER_URL)
    
    if not tools:
        print("No se encontraron tools disponibles")
        return
    
    # Probar algunas tools
    if any(tool["name"] == "add" for tool in tools):
        call_tool(SERVER_URL, "add", {"a": 40, "b": 2})
    
    if any(tool["name"] == "multiply" for tool in tools):
        call_tool(SERVER_URL, "multiply", {"a": 6, "b": 7})
    
    if any(tool["name"] == "greet" for tool in tools):
        call_tool(SERVER_URL, "greet", {"name": "Usuario"})
    
    # Probar un caso de error
    if any(tool["name"] == "divide" for tool in tools):
        call_tool(SERVER_URL, "divide", {"a": 10, "b": 0})
    
    # Enviar ping
    ping_server(SERVER_URL)
    
    print("\nPrueba completada")

if __name__ == "__main__":
    main()