"""
Implementación del transporte HTTP para MCP usando FastAPI.
"""
import sys
import json
import logging
import threading
import time
import asyncio
from typing import Dict, Any, Optional, List, Union, Callable

try:
    import uvicorn
    from fastapi import FastAPI, Request, Response, HTTPException, Depends, Header
    from fastapi.responses import JSONResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.background import BackgroundTask
except ImportError:
    raise ImportError(
        "Para usar el transporte HTTP, instala las dependencias requeridas: "
        "pip install fastapi uvicorn"
    )

logger = logging.getLogger("mcp_server.transport.http")

class FastAPITransport:
    """
    Implementa el transporte HTTP/HTTPS para MCP usando FastAPI.
    """
    
    def __init__(
        self,
        mcp_server,
        host: str = "localhost",
        port: int = 8000,
        use_https: bool = False,
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None
    ):
        """
        Inicializa el transporte HTTP.
        
        Args:
            mcp_server: Instancia del servidor MCP
            host: Host para escuchar
            port: Puerto para escuchar
            use_https: Usar HTTPS en lugar de HTTP
            cert_file: Ruta al archivo de certificado (solo para HTTPS)
            key_file: Ruta al archivo de clave privada (solo para HTTPS)
        """
        self.mcp_server = mcp_server
        self.host = host
        self.port = port
        self.use_https = use_https
        self.cert_file = cert_file
        self.key_file = key_file
        
        # Crear aplicación FastAPI
        self.app = FastAPI(title="InstantNeo MCP Server")
        
        # Configurar CORS
        cors_origins = mcp_server.config.get("http", {}).get("cors_origins", ["*"])
        if cors_origins:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        
        # Configurar rutas
        self._setup_routes()
        
        # Estado del servidor
        self.server = None
        self.server_thread = None
        self.running = False
        
        # Almacenamiento de sesiones SSE
        self.sse_connections = {}
    
    def _setup_routes(self):
        """
        Configura las rutas de la API.
        """
        # Endpoint principal para JSON-RPC
        @self.app.post("/mcp")
        async def handle_jsonrpc(request: Request):
            print("📥 ¡Entró a handle_jsonrpc!", file=sys.stderr)
            # Leer el cuerpo de la solicitud
            body = await request.body()
            message_str = body.decode("utf-8")
            
            # Verificar autenticación si está habilitada
            auth_config = self.mcp_server.config.get("http", {}).get("auth", {})
            if auth_config.get("enabled", False):
                # Implementar verificación de autenticación aquí
                pass
            
            # Procesar mensaje
            response_str = self.mcp_server.handle_message(message_str)
            
            
            # Si no hay respuesta (notificación), devolver 202 Accepted
            if response_str is None:
                return Response(status_code=202)
            
            # Devolver respuesta JSON
            return Response(
                content=response_str,
                media_type="application/json"
            )
        
        # Endpoint para SSE (Server-Sent Events)
        @self.app.get("/mcp")
        async def handle_sse(request: Request):
            # Verificar que el cliente acepta SSE
            accept_header = request.headers.get("accept", "")
            if "text/event-stream" not in accept_header:
                raise HTTPException(
                    status_code=406,
                    detail="Client must accept text/event-stream"
                )
            
            # Verificar autenticación si está habilitada
            auth_config = self.mcp_server.config.get("http", {}).get("auth", {})
            if auth_config.get("enabled", False):
                # Implementar verificación de autenticación aquí
                pass
            
            # Crear conexión SSE
            connection_id = f"sse_{time.time()}_{id(request)}"
            
            # Función para generar eventos SSE
            async def event_generator():
                try:
                    # Enviar evento inicial
                    yield f"id: {connection_id}\n"
                    yield f"event: connected\n"
                    yield f"data: {json.dumps({'connectionId': connection_id})}\n\n"
                    
                    # Crear cola de mensajes para esta conexión
                    queue = asyncio.Queue()
                    self.sse_connections[connection_id] = queue
                    
                    # Mantener conexión abierta y enviar mensajes cuando lleguen
                    while True:
                        # Esperar mensaje o enviar keep-alive cada 30 segundos
                        try:
                            message = await asyncio.wait_for(queue.get(), timeout=30)
                            
                            # Si el mensaje es None, cerrar conexión
                            if message is None:
                                break
                                
                            # Enviar mensaje como evento SSE
                            yield f"id: {connection_id}_{int(time.time())}\n"
                            yield f"data: {message}\n\n"
                            
                        except asyncio.TimeoutError:
                            # Enviar comentario como keep-alive
                            yield ": keep-alive\n\n"
                            
                except asyncio.CancelledError:
                    logger.info(f"Conexión SSE {connection_id} cancelada")
                except Exception as e:
                    logger.exception(f"Error en conexión SSE {connection_id}")
                finally:
                    # Limpiar conexión
                    self.sse_connections.pop(connection_id, None)
                    logger.info(f"Conexión SSE {connection_id} cerrada")
            
            # Devolver respuesta SSE
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
            )
        
        # Endpoint para cerrar sesión
        @self.app.delete("/mcp")
        async def handle_session_close(request: Request):
            # Verificar autenticación si está habilitada
            auth_config = self.mcp_server.config.get("http", {}).get("auth", {})
            if auth_config.get("enabled", False):
                # Implementar verificación de autenticación aquí
                pass
            
            # Obtener ID de sesión
            session_id = request.headers.get("Mcp-Session-Id")
            if session_id and session_id in self.mcp_server.sessions:
                # Eliminar sesión
                self.mcp_server.sessions.pop(session_id, None)
                logger.info(f"Sesión {session_id} cerrada explícitamente")
                return Response(status_code=204)  # No Content
            
            # Si no se encuentra la sesión, devolver 404
            return Response(status_code=404)
    
    def start(self):
        print("✅ InstantMCPServer arrancado desde http", file=sys.stderr)
        """
        Inicia el servidor HTTP/HTTPS.
        """
        if self.running:
            logger.warning("El servidor HTTP ya está en ejecución")
            return
        
        self.running = True
        
        # Configurar opciones de Uvicorn
        uvicorn_config = {
            "app": self.app,
            "host": self.host,
            "port": self.port,
            "log_level": "info"
        }
        
        # Añadir configuración SSL si es necesario
        if self.use_https:
            if not self.cert_file or not self.key_file:
                raise ValueError("Para usar HTTPS, se requieren cert_file y key_file")
            
            uvicorn_config["ssl_certfile"] = self.cert_file
            uvicorn_config["ssl_keyfile"] = self.key_file
        
        # Iniciar servidor en un hilo separado
        def run_server():
            self.server = uvicorn.Server(uvicorn.Config(**uvicorn_config))
            self.server.run()
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        # Esperar a que el servidor esté listo
        time.sleep(1)
        
        logger.info(f"Servidor HTTP{'S' if self.use_https else ''} iniciado en {self.host}:{self.port}")
    
    def stop(self):
        """
        Detiene el servidor HTTP/HTTPS.
        """
        if not self.running:
            logger.warning("El servidor HTTP no está en ejecución")
            return
        
        self.running = False
        
        # Cerrar todas las conexiones SSE
        for connection_id, queue in list(self.sse_connections.items()):
            try:
                queue.put_nowait(None)  # Señal para cerrar conexión
            except Exception:
                pass
        
        # Detener servidor
        if self.server:
            self.server.should_exit = True
        
        # Esperar a que el hilo termine
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5)
        
        logger.info("Servidor HTTP detenido")
    
    def send_notification(self, connection_id: str, message: str):
        """
        Envía una notificación a una conexión SSE.
        
        Args:
            connection_id: ID de la conexión
            message: Mensaje a enviar
        """
        queue = self.sse_connections.get(connection_id)
        if queue:
            try:
                asyncio.run_coroutine_threadsafe(
                    queue.put(message),
                    asyncio.get_event_loop()
                )
                return True
            except Exception as e:
                logger.exception(f"Error al enviar notificación a {connection_id}")
        
        return False
    
    def broadcast_notification(self, message: str):
        """
        Envía una notificación a todas las conexiones SSE.
        
        Args:
            message: Mensaje a enviar
        """
        for connection_id, queue in list(self.sse_connections.items()):
            try:
                asyncio.run_coroutine_threadsafe(
                    queue.put(message),
                    asyncio.get_event_loop()
                )
            except Exception:
                pass