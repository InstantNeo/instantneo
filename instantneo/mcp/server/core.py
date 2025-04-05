"""
Implementación principal del servidor MCP para InstantNeo.
"""
import json
import sys
import time
import uuid
import threading
import logging
from typing import Dict, Any, Optional, List, Union, Type

from ..common.config import get_default_config, merge_configs
from ..common.converters import skill_metadata_to_mcp_tool, mcp_tool_result_to_response
from .transport.http import FastAPITransport
from .transport.stdio import StdioTransport
from .handlers import tools, lifecycle, errors

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mcp_server")

class InstantMCPServer:
    """
    Servidor MCP que expone skills de InstantNeo como tools MCP.
    
    Esta clase permite crear un servidor compatible con el Model Context Protocol (MCP)
    a partir de un SkillManager de InstantNeo, exponiendo las skills registradas como
    tools MCP que pueden ser consumidas por clientes MCP.
    
    Attributes:
        skill_manager: Instancia de SkillManager con skills registradas
        config: Configuración del servidor
        transports: Lista de transportes activos
        sessions: Diccionario de sesiones activas
        tools_cache: Caché de tools MCP generadas a partir de skills
        running: Estado del servidor
    """
    
    def __init__(self, skill_manager, environment="development", config=None):
        """
        Inicializa el servidor MCP.
        
        Args:
            skill_manager: Instancia de SkillManager con skills registradas
            environment: Entorno de ejecución ("development", "production", "testing")
            config: Configuración personalizada (opcional)
        """
        self.skill_manager = skill_manager
        
        # Cargar configuración
        base_config = get_default_config(environment)
        self.config = merge_configs(base_config, config or {})
        
        # Inicializar transportes
        self.transports = []
        
        # Almacenamiento de sesiones y tokens
        self.sessions = {}
        
        # Caché de tools
        self.tools_cache = None
        
        # Estado del servidor
        self.running = False
        
        logger.info(f"InstantMCPServer inicializado en entorno {environment}")
        
    def start(self):
        """
        Inicia el servidor según la configuración.
        
        Returns:
            self: Para permitir encadenamiento de métodos
        """
        if self.running:
            logger.warning("El servidor ya está en ejecución")
            return self
            
        self.running = True
        
        # Iniciar transportes según configuración
        self._setup_transports()
        
        # Iniciar limpieza periódica
        self._setup_cleanup()
        
        logger.info("Servidor MCP iniciado")
        return self
        
    def stop(self):
        """
        Detiene el servidor y todos sus transportes.
        """
        if not self.running:
            logger.warning("El servidor no está en ejecución")
            return
            
        self.running = False
        
        # Detener todos los transportes
        for transport in self.transports:
            transport.stop()
            
        # Limpiar recursos
        self.sessions.clear()
        
        logger.info("Servidor MCP detenido")
            
    def _setup_transports(self):
        """
        Configura e inicia los transportes según la configuración.
        """
        # Limpiar transportes existentes
        for transport in self.transports:
            transport.stop()
        self.transports = []
        
        # Configurar transporte HTTP si está habilitado
        if self.config.get("http", {}).get("enabled", True):
            http_config = self.config.get("http", {})
            transport = FastAPITransport(
                mcp_server=self,
                host=http_config.get("host", "localhost"),
                port=http_config.get("port", 8000),
                use_https=http_config.get("use_https", False),
                cert_file=http_config.get("cert_file"),
                key_file=http_config.get("key_file")
            )
            transport.start()
            self.transports.append(transport)
            logger.info(f"Transporte HTTP iniciado en {http_config.get('host', 'localhost')}:{http_config.get('port', 8000)}")
        
        # Configurar transporte stdio si está habilitado
        if self.config.get("stdio", {}).get("enabled", False):
            transport = StdioTransport(mcp_server=self)
            transport.start()
            self.transports.append(transport)
            logger.info("Transporte stdio iniciado")
            
    def _setup_cleanup(self):
        """
        Configura la limpieza periódica de sesiones y recursos.
        """
        def cleanup_task():
            while self.running:
                # Limpiar sesiones expiradas
                current_time = time.time()
                expired_sessions = []
                
                for session_id, session in self.sessions.items():
                    if session.get("expires_at", float("inf")) < current_time:
                        expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    self.sessions.pop(session_id, None)
                    
                if expired_sessions:
                    logger.info(f"Limpiadas {len(expired_sessions)} sesiones expiradas")
                
                # Esperar hasta la próxima limpieza
                time.sleep(self.config.get("cleanup_interval", 300))  # 5 minutos por defecto
        
        # Iniciar hilo de limpieza
        cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
        cleanup_thread.start()
        
    def handle_message(self, message_str):
        """
        Procesa un mensaje entrante y determina cómo responder.
        
        Args:
            message_str: Mensaje JSON-RPC como string
            
        Returns:
            str: Respuesta JSON-RPC como string
        """

        try:
            # Parsear mensaje JSON-RPC
            message = json.loads(message_str)
            
            # Determinar tipo de mensaje
            if isinstance(message, list):
                # Batch de mensajes
                responses = []
                for msg in message:
                    if "id" in msg:
                        # Es un request
                        response = self._handle_request(msg)
                        responses.append(response)
                    else:
                        # Es una notificación, no requiere respuesta
                        self._handle_notification(msg)
                
                if responses:
                    return json.dumps(responses)
                return None
            elif "id" in message:
                # Es un request individual
                response = self._handle_request(message)
                return json.dumps(response)
            else:
                # Es una notificación individual
                self._handle_notification(message)
                return None
                
        except json.JSONDecodeError:
            # Error de parseo JSON
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                },
                "id": None
            }
            
            return json.dumps(error_response)
        except Exception as e:
            # Error interno
            logger.exception("Error al procesar mensaje")
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": str(e)
                },
                "id": None
            }
            return json.dumps(error_response)
            
    def _handle_request(self, request):
        """
        Maneja una solicitud JSON-RPC.
        
        Args:
            request: Objeto de solicitud JSON-RPC
            
        Returns:
            dict: Objeto de respuesta JSON-RPC
        """
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")
        
        # Enrutar a manejador correspondiente
        if method == "initialize":
            return lifecycle.handle_initialize(self, params, request_id)
        elif method == "ping":
            return lifecycle.handle_ping(request_id)
        elif method == "tools/list":
            return tools.handle_list_tools(self, params, request_id)
        elif method == "tools/call":
            return tools.handle_call_tool(self, params, request_id)
        else:
            # Método no encontrado
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                },
                "id": request_id
            }
            
    def _handle_notification(self, notification):
        """
        Maneja una notificación JSON-RPC.
        
        Args:
            notification: Objeto de notificación JSON-RPC
        """
        method = notification.get("method", "")
        params = notification.get("params", {})
        
        if method == "notifications/initialized":
            lifecycle.handle_initialized(self, params)
        elif method == "notifications/cancelled":
            # Manejar cancelación de solicitud
            pass
        else:
            logger.warning(f"Notificación no manejada: {method}")
            
    def get_tools(self, refresh=False):
        """
        Obtiene la lista de tools MCP generadas a partir de las skills registradas.
        
        Args:
            refresh: Si es True, regenera la caché de tools
            
        Returns:
            list: Lista de objetos tool MCP
        """
        if self.tools_cache is None or refresh:
            # Generar tools a partir de skills
            tools_list = []
            
            for skill_name in self.skill_manager.get_skill_names():
                metadata = self.skill_manager.get_skill_metadata_by_name(skill_name)
                if metadata:
                    tool = skill_metadata_to_mcp_tool(skill_name, metadata)
                    tools_list.append(tool)
            
            self.tools_cache = tools_list
            
        return self.tools_cache
        
    def execute_tool(self, tool_name, arguments):
        """
        Ejecuta una tool MCP (skill) con los argumentos proporcionados.
        
        Args:
            tool_name: Nombre de la tool/skill a ejecutar
            arguments: Argumentos para la tool
            
        Returns:
            dict: Resultado de la ejecución en formato MCP
        """
        try:
            # Obtener la skill
            skill = self.skill_manager.get_skill_by_name(tool_name)
            
            if skill is None:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error: Tool '{tool_name}' not found"
                        }
                    ],
                    "isError": True
                }
                
            # Si es un diccionario (caso de duplicados), tomar el primero
            if isinstance(skill, dict):
                skill = next(iter(skill.values()))
                
            # Ejecutar la skill
            result = skill(**arguments)
            
            # Convertir resultado a formato MCP
            return mcp_tool_result_to_response(result)
            
        except Exception as e:
            logger.exception(f"Error al ejecutar tool {tool_name}")
            
            # Devolver error como resultado de la herramienta
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error al ejecutar la herramienta: {str(e)}"
                    }
                ],
                "isError": True
            }
    
    def _get_current_time(self):
        """
        Obtiene el tiempo actual en segundos desde la época.
        
        Returns:
            float: Tiempo actual
        """
        return time.time()
    
    def run(self):
        """
        Inicia el servidor y lo mantiene en ejecución.
        """
        self.start()
        
        try:
            # Mantener el hilo principal vivo
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Deteniendo servidor MCP por interrupción de teclado...")
        finally:
            self.stop()