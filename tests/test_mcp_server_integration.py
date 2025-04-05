"""
Pruebas de integración para el servidor MCP.
"""
import unittest
import json
import time
import threading
import requests
from unittest.mock import MagicMock

from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

class TestMCPServerIntegration(unittest.TestCase):
    """Pruebas de integración para el servidor MCP."""
    
    @classmethod
    def setUpClass(cls):
        """Configuración para todas las pruebas."""
        # Definir skills de prueba
        @skill(
            description="Suma dos números",
            parameters={
                "a": "Primer número",
                "b": "Segundo número"
            },
            tags=["math", "arithmetic"]
        )
        def add(a: int, b: int) -> int:
            return a + b
        
        @skill(
            description="Concatena dos cadenas",
            parameters={
                "str1": "Primera cadena",
                "str2": "Segunda cadena"
            },
            tags=["text"]
        )
        def concat(str1: str, str2: str) -> str:
            return str1 + str2
        
        # Crear SkillManager y registrar skills
        cls.skill_manager = SkillManager()
        cls.skill_manager.register_skill(add)
        cls.skill_manager.register_skill(concat)
        
        # Configuración del servidor
        config = {
            "http": {
                "host": "localhost",
                "port": 8765,  # Puerto diferente para evitar conflictos
                "cors_origins": ["*"]
            },
            "stdio": {
                "enabled": False
            }
        }
        
        # Crear e iniciar servidor
        cls.server = InstantMCPServer(cls.skill_manager, environment="testing", config=config)
        cls.server_thread = threading.Thread(target=cls.server.run)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        
        # Esperar a que el servidor esté listo
        time.sleep(2)
        
        # URL base para las solicitudes
        cls.base_url = "http://localhost:8765/mcp"
    
    @classmethod
    def tearDownClass(cls):
        """Limpieza después de todas las pruebas."""
        cls.server.stop()
        cls.server_thread.join(timeout=5)
    
    def send_jsonrpc_request(self, method, params=None, request_id=1):
        """Envía una solicitud JSON-RPC al servidor."""
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id
        }
        
        if params is not None:
            request["params"] = params
        
        response = requests.post(self.base_url, json=request)
        return response.json()
    
    def test_initialize(self):
        """Prueba la inicialización del servidor."""
        params = {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {
                "name": "TestClient",
                "version": "1.0.0"
            }
        }
        
        response = self.send_jsonrpc_request("initialize", params)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertIn("protocolVersion", response["result"])
        self.assertIn("capabilities", response["result"])
        self.assertIn("serverInfo", response["result"])
        
        # Enviar notificación initialized
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        
        response = requests.post(self.base_url, json=notification)
        self.assertEqual(response.status_code, 202)  # Accepted
    
    def test_list_tools(self):
        """Prueba el listado de tools."""
        response = self.send_jsonrpc_request("tools/list", {}, 2)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 2)
        self.assertIn("tools", response["result"])
        
        tools = response["result"]["tools"]
        self.assertEqual(len(tools), 2)
        
        # Verificar que las tools esperadas están presentes
        tool_names = [tool["name"] for tool in tools]
        self.assertIn("add", tool_names)
        self.assertIn("concat", tool_names)
    
    def test_call_tool(self):
        """Prueba la llamada a una tool."""
        params = {
            "name": "add",
            "arguments": {
                "a": 40,
                "b": 2
            }
        }
        
        response = self.send_jsonrpc_request("tools/call", params, 3)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 3)
        self.assertIn("content", response["result"])
        
        content = response["result"]["content"]
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[0]["text"], "42")
        
        # Probar otra tool
        params = {
            "name": "concat",
            "arguments": {
                "str1": "Hello, ",
                "str2": "World!"
            }
        }
        
        response = self.send_jsonrpc_request("tools/call", params, 4)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 4)
        self.assertIn("content", response["result"])
        
        content = response["result"]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[0]["text"], "Hello, World!")
    
    def test_ping(self):
        """Prueba el ping al servidor."""
        response = self.send_jsonrpc_request("ping", {}, 5)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 5)
        self.assertEqual(response["result"], {})
    
    def test_method_not_found(self):
        """Prueba la respuesta a un método inexistente."""
        response = self.send_jsonrpc_request("non_existent_method", {}, 6)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 6)
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32601)  # Method not found
    
    def test_invalid_params(self):
        """Prueba la respuesta a parámetros inválidos."""
        params = {
            "name": "add",
            "arguments": {
                "a": 40
                # Falta el parámetro 'b'
            }
        }
        
        response = self.send_jsonrpc_request("tools/call", params, 7)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 7)
        self.assertIn("content", response["result"])
        self.assertTrue(response["result"]["isError"])

if __name__ == "__main__":
    unittest.main()