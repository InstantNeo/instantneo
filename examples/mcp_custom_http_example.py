#!/usr/bin/env python3
"""
Ejemplo de InstantMCPServer con configuración HTTP personalizada.

Este ejemplo muestra cómo configurar un servidor MCP con opciones HTTP personalizadas,
como host, puerto y CORS.

Para ejecutar:
    python examples/mcp_custom_http_example.py
"""

import time
from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Definir skills
@skill(
    description="Concatena dos cadenas de texto",
    parameters={
        "text1": "Primera cadena de texto",
        "text2": "Segunda cadena de texto"
    }
)
def concatenate(text1: str, text2: str) -> str:
    return text1 + text2

@skill(
    description="Convierte texto a mayúsculas",
    parameters={
        "text": "Texto a convertir"
    }
)
def to_uppercase(text: str) -> str:
    return text.upper()

def main():
    # Crear y configurar SkillManager
    skill_manager = SkillManager()
    skill_manager.register_skill(concatenate)
    skill_manager.register_skill(to_uppercase)
    
    #print(f"Skills registradas: {skill_manager.get_skill_names()}")
    
    # Configuración personalizada
    config = {
        "server_name": "Servidor de Texto",
        "http": {
            "host": "0.0.0.0",  # Accesible desde cualquier IP
            "port": 9000,       # Puerto personalizado
            "cors_origins": ["http://localhost:3000"]  # Permitir solo este origen
        }
    }
    
    # Crear servidor MCP con configuración personalizada
    server = InstantMCPServer(skill_manager, config=config)
    
    # Iniciar el servidor (sin bloquear)
    server.start()
    
    print(f"Servidor iniciado en http://{config['http']['host']}:{config['http']['port']}/mcp")
    print("Presiona Ctrl+C para detener el servidor")
    
    try:
        # Mantener el servidor en ejecución
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Deteniendo servidor...")
    finally:
        server.stop()
        print("Servidor detenido")

if __name__ == "__main__":
    main()