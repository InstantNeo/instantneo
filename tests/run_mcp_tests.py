"""
Script para ejecutar todas las pruebas del servidor MCP.

Este script ejecuta:
1. Pruebas unitarias
2. Pruebas de integración
3. Ejemplos de cliente y servidor

Uso:
    python tests/run_mcp_tests.py
"""

import os
import sys
import unittest
import subprocess
import time
import signal
import threading
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mcp_tests")

def run_unittest(test_module):
    """
    Ejecuta un módulo de prueba unitaria.
    
    Args:
        test_module: Nombre del módulo de prueba
        
    Returns:
        bool: True si todas las pruebas pasaron, False en caso contrario
    """
    logger.info(f"Ejecutando pruebas en {test_module}")
    
    try:
        # Ejecutar pruebas directamente con unittest
        if test_module == "tests.test_mcp_server_unit":
            import test_mcp_server_unit as module
        elif test_module == "tests.test_mcp_server_integration":
            import test_mcp_server_integration as module
        else:
            logger.error(f"Módulo de prueba desconocido: {test_module}")
            return False
        
        # Crear y ejecutar suite de pruebas
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        
        # Verificar resultado
        if result.wasSuccessful():
            logger.info(f"Todas las pruebas en {test_module} pasaron correctamente")
            return True
        else:
            logger.error(f"Algunas pruebas en {test_module} fallaron")
            return False
    except Exception as e:
        logger.exception(f"Error al ejecutar pruebas en {test_module}: {e}")
        return False

def run_example_server():
    """
    Ejecuta el servidor MCP de ejemplo en un proceso separado.
    
    Returns:
        subprocess.Popen: Proceso del servidor
    """
    logger.info("Iniciando servidor MCP de ejemplo")
    
    try:
        # Ejecutar el servidor en un proceso separado
        server_process = subprocess.Popen(
            [sys.executable, "examples/mcp_server_example.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Esperar a que el servidor esté listo
        time.sleep(3)
        
        logger.info("Servidor MCP de ejemplo iniciado")
        return server_process
    except Exception as e:
        logger.exception(f"Error al iniciar servidor MCP de ejemplo: {e}")
        return None

def run_example_client():
    """
    Ejecuta el cliente MCP de ejemplo.
    
    Returns:
        bool: True si el cliente se ejecutó correctamente, False en caso contrario
    """
    logger.info("Ejecutando cliente MCP de ejemplo")
    
    try:
        # Ejecutar el cliente
        result = subprocess.run(
            [sys.executable, "examples/mcp_client_example.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        # Mostrar salida del cliente
        logger.info("Salida del cliente MCP:")
        for line in result.stdout.splitlines():
            logger.info(f"  {line}")
        
        logger.info("Cliente MCP de ejemplo ejecutado correctamente")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error al ejecutar cliente MCP de ejemplo: {e}")
        logger.error(f"Salida estándar: {e.stdout}")
        logger.error(f"Salida de error: {e.stderr}")
        return False
    except Exception as e:
        logger.exception(f"Error al ejecutar cliente MCP de ejemplo: {e}")
        return False

def main():
    """Función principal."""
    logger.info("Iniciando pruebas del servidor MCP")
    
    # Ejecutar pruebas unitarias
    unit_tests_passed = run_unittest("tests.test_mcp_server_unit")
    
    # Ejecutar pruebas de integración
    integration_tests_passed = run_unittest("tests.test_mcp_server_integration")
    
    # Ejecutar ejemplos
    server_process = run_example_server()
    
    if server_process:
        try:
            # Ejecutar cliente
            client_passed = run_example_client()
        finally:
            # Detener servidor
            logger.info("Deteniendo servidor MCP de ejemplo")
            server_process.terminate()
            server_process.wait(timeout=5)
            logger.info("Servidor MCP de ejemplo detenido")
    else:
        client_passed = False
    
    # Mostrar resumen
    logger.info("\nResumen de pruebas:")
    logger.info(f"Pruebas unitarias: {'PASARON' if unit_tests_passed else 'FALLARON'}")
    logger.info(f"Pruebas de integración: {'PASARON' if integration_tests_passed else 'FALLARON'}")
    logger.info(f"Ejemplo cliente-servidor: {'PASÓ' if client_passed else 'FALLÓ'}")
    
    # Determinar resultado final
    all_passed = unit_tests_passed and integration_tests_passed and client_passed
    
    if all_passed:
        logger.info("\n¡TODAS LAS PRUEBAS PASARON CORRECTAMENTE!")
        return 0
    else:
        logger.error("\nALGUNAS PRUEBAS FALLARON")
        return 1

if __name__ == "__main__":
    sys.exit(main())