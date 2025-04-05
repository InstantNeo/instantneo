"""
Pruebas unitarias para los componentes del servidor MCP.
"""
import unittest
import json
from unittest.mock import MagicMock, patch

from instantneo.skills import skill, SkillManager
from instantneo.mcp.common.converters import skill_metadata_to_mcp_tool, mcp_tool_result_to_response
from instantneo.mcp.common.jsonrpc import create_request, create_response, create_error_response
from instantneo.mcp.server.handlers import tools, lifecycle, errors

class TestConverters(unittest.TestCase):
    """Pruebas para los conversores de skills a tools MCP."""
    
    def setUp(self):
        """Configuración para las pruebas."""
        # Definir una skill de ejemplo
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
        
        self.add_skill = add
        self.add_metadata = add.skill_metadata
    
    def test_skill_to_tool_conversion(self):
        """Prueba la conversión de skill a tool MCP."""
        # Convertir skill a tool
        tool = skill_metadata_to_mcp_tool("add", self.add_metadata)
        
        # Verificar estructura básica
        self.assertEqual(tool["name"], "add")
        self.assertEqual(tool["description"], "Suma dos números")
        self.assertEqual(tool["inputSchema"]["type"], "object")
        
        # Verificar propiedades
        properties = tool["inputSchema"]["properties"]
        self.assertIn("a", properties)
        self.assertIn("b", properties)
        self.assertEqual(properties["a"]["type"], "integer")
        self.assertEqual(properties["a"]["description"], "Primer número")
        
        # Verificar parámetros requeridos
        self.assertIn("required", tool["inputSchema"])
        self.assertIn("a", tool["inputSchema"]["required"])
        self.assertIn("b", tool["inputSchema"]["required"])
        
        # Verificar anotaciones
        self.assertIn("annotations", tool)
        self.assertIn("tags", tool["annotations"])
        self.assertIn("math", tool["annotations"]["tags"])
    
    def test_result_to_response_conversion(self):
        """Prueba la conversión de resultados a respuestas MCP."""
        # Probar con un resultado simple
        result = 42
        response = mcp_tool_result_to_response(result)
        
        self.assertIn("content", response)
        self.assertEqual(len(response["content"]), 1)
        self.assertEqual(response["content"][0]["type"], "text")
        self.assertEqual(response["content"][0]["text"], "42")
        self.assertEqual(response["isError"], False)
        
        # Probar con un error
        try:
            raise ValueError("Error de prueba")
        except ValueError as e:
            response = mcp_tool_result_to_response(e)
            
        self.assertIn("content", response)
        self.assertEqual(response["content"][0]["type"], "text")
        self.assertIn("Error de prueba", response["content"][0]["text"])
        self.assertEqual(response["isError"], True)

class TestJSONRPC(unittest.TestCase):
    """Pruebas para las utilidades JSON-RPC."""
    
    def test_create_request(self):
        """Prueba la creación de solicitudes JSON-RPC."""
        request = create_request("test_method", {"param1": "value1"}, 123)
        
        self.assertEqual(request["jsonrpc"], "2.0")
        self.assertEqual(request["method"], "test_method")
        self.assertEqual(request["params"]["param1"], "value1")
        self.assertEqual(request["id"], 123)
    
    def test_create_response(self):
        """Prueba la creación de respuestas JSON-RPC."""
        response = create_response({"result": "success"}, 123)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["result"]["result"], "success")
        self.assertEqual(response["id"], 123)
    
    def test_create_error_response(self):
        """Prueba la creación de respuestas de error JSON-RPC."""
        error = create_error_response(-32601, "Method not found", 123)
        
        self.assertEqual(error["jsonrpc"], "2.0")
        self.assertEqual(error["error"]["code"], -32601)
        self.assertEqual(error["error"]["message"], "Method not found")
        self.assertEqual(error["id"], 123)

class TestHandlers(unittest.TestCase):
    """Pruebas para los manejadores del servidor MCP."""
    
    def setUp(self):
        """Configuración para las pruebas."""
        # Crear un SkillManager mock
        self.skill_manager = MagicMock()
        self.skill_manager.get_skill_names.return_value = ["add", "subtract"]
        
        # Crear metadatos de skill mock
        add_metadata = {
            "name": "add",
            "description": "Suma dos números",
            "parameters": {
                "a": {"type": "int", "description": "Primer número"},
                "b": {"type": "int", "description": "Segundo número"}
            },
            "required": ["a", "b"],
            "tags": ["math"]
        }
        
        self.skill_manager.get_skill_metadata_by_name.return_value = add_metadata
        
        # Crear una función mock para la skill
        add_func = MagicMock()
        add_func.return_value = 42
        self.skill_manager.get_skill_by_name.return_value = add_func
        
        # Crear un servidor mock
        self.server = MagicMock()
        self.server.skill_manager = self.skill_manager
        self.server.get_tools.return_value = [
            skill_metadata_to_mcp_tool("add", add_metadata)
        ]
        self.server.execute_tool.return_value = {"content": [{"type": "text", "text": "42"}], "isError": False}
        self.server._get_current_time.return_value = 1000000
        self.server.config = {
            "protocol_version": "2025-03-26",
            "server_name": "Test Server",
            "server_version": "1.0.0"
        }
        self.server.sessions = {}
    
    def test_list_tools_handler(self):
        """Prueba el manejador de listado de tools."""
        response = tools.handle_list_tools(self.server, {}, 1)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertIn("tools", response["result"])
        self.assertEqual(len(response["result"]["tools"]), 1)
        self.assertEqual(response["result"]["tools"][0]["name"], "add")
    
    def test_call_tool_handler(self):
        """Prueba el manejador de llamada a tools."""
        params = {
            "name": "add",
            "arguments": {"a": 20, "b": 22}
        }
        
        response = tools.handle_call_tool(self.server, params, 2)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 2)
        self.assertIn("content", response["result"])
        
        # Verificar que se llamó a execute_tool
        self.server.execute_tool.assert_called_once_with("add", {"a": 20, "b": 22})
    
    def test_initialize_handler(self):
        """Prueba el manejador de inicialización."""
        params = {
            "protocolVersion": "2025-03-26",
            "capabilities": {"sampling": {}},
            "clientInfo": {"name": "Test Client", "version": "1.0.0"}
        }
        
        response = lifecycle.handle_initialize(self.server, params, 3)
        
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 3)
        self.assertEqual(response["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("capabilities", response["result"])
        self.assertIn("serverInfo", response["result"])
        
        # Verificar que se creó una sesión
        self.assertEqual(len(self.server.sessions), 1)

if __name__ == "__main__":
    unittest.main()