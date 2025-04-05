"""
Implementación del transporte stdio para MCP.
"""
import sys
import json
import threading
import logging
import time
from typing import Dict, Any, Optional, List, Union, Callable

logger = logging.getLogger("mcp_server.transport.stdio")

class StdioTransport:
    """
    Implementa el transporte stdio para MCP.
    """
    
    def __init__(self, mcp_server):
        """
        Inicializa el transporte stdio.
        
        Args:
            mcp_server: Instancia del servidor MCP
        """
        self.mcp_server = mcp_server
        self.running = False
        self.io_thread = None
    
    def start(self):
        print("✅ InstantMCPServer arrancado desde stdio", file=sys.stderr)
        """
        Inicia el servidor stdio.
        """
        if self.running:
            logger.warning("El servidor stdio ya está en ejecución")
            return
        
        self.running = True
        
        # Iniciar hilo de lectura/escritura
        self.io_thread = threading.Thread(target=self._stdio_loop, daemon=True)
        self.io_thread.start()
        
        logger.info("Servidor stdio iniciado")
    
    def stop(self):
        """
        Detiene el servidor stdio.
        """
        if not self.running:
            logger.warning("El servidor stdio no está en ejecución")
            return
        
        self.running = False
        
        # No es necesario cerrar stdin/stdout, ya que son manejados por el sistema
        
        # Esperar a que el hilo termine
        if self.io_thread and self.io_thread.is_alive():
            self.io_thread.join(timeout=5)
        
        logger.info("Servidor stdio detenido")
    
    def _stdio_loop(self):
        """
        Bucle principal de lectura/escritura.
        """
        try:
            # Configurar stdin para lectura no bloqueante
            # Nota: Esto solo funciona en sistemas Unix
            import fcntl
            import os
            
            fd = sys.stdin.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        except (ImportError, AttributeError):
            # En Windows o si fcntl no está disponible, usar lectura bloqueante
            pass
        
        buffer = ""
        
        while self.running:
            try:
                # Leer de stdin
                try:
                    chunk = sys.stdin.read(1024)
                    if not chunk:  # EOF
                        if self.running:
                            logger.info("EOF en stdin, deteniendo servidor")
                            self.running = False
                        break
                    
                    buffer += chunk
                except (IOError, OSError):
                    # No hay datos disponibles, esperar un poco
                    time.sleep(0.1)
                    continue
                
                # Procesar líneas completas
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        self._process_line(line)
            
            except Exception as e:
                logger.exception(f"Error en bucle stdio: {str(e)}")
                # Continuar para mantener el servidor en ejecución
        
        logger.info("Bucle stdio finalizado")
    
    def _process_line(self, line: str):
        """
        Procesa una línea de entrada.
        
        Args:
            line: Línea a procesar
        """
        try:
            # Procesar mensaje
            response_str = self.mcp_server.handle_message(line)
            
            # Si hay respuesta, escribirla a stdout
            if response_str:
                sys.stdout.write(response_str + "\n")
                sys.stdout.flush()
        
        except Exception as e:
            logger.exception(f"Error al procesar línea: {str(e)}")
            
            # Intentar enviar respuesta de error
            try:
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": "Internal error",
                        "data": str(e)
                    },
                    "id": None
                }
                
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()
            except Exception:
                # Si no podemos enviar la respuesta, registrar y continuar
                logger.exception("Error al enviar respuesta de error")