#!/usr/bin/env python3
"""
Ejemplo de InstantMCPServer con autenticación API Key.

Este ejemplo muestra cómo configurar un servidor MCP con autenticación mediante API Keys
para proteger el acceso a las skills.

Para ejecutar:
    python examples/mcp_api_key_auth_example.py
"""

import time
from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Definir skills
@skill(
    description="Procesa datos confidenciales",
    parameters={
        "data": "Datos a procesar"
    }
)
def process_data(data: str) -> str:
    return f"Datos procesados: {data}"

@skill(
    description="Obtiene información sensible",
    parameters={
        "id": "Identificador de la información"
    }
)
def get_sensitive_info(id: str) -> dict:
    # Simulación de acceso a datos sensibles
    return {
        "id": id,
        "timestamp": time.time(),
        "status": "authorized",
        "data": f"Información confidencial para ID: {id}"
    }

def main():
    # Crear y configurar SkillManager
    skill_manager = SkillManager()
    skill_manager.register_skill(process_data)
    skill_manager.register_skill(get_sensitive_info)
    
    #print(f"Skills registradas: {skill_manager.get_skill_names()}")
    
    # Configuración con autenticación
    config = {
        "server_name": "Servidor Seguro",
        "http": {
            "host": "localhost",
            "port": 8000,
            "auth": {
                "enabled": True,
                "type": "api_key",
                "api_keys": ["sk_test_12345", "sk_live_67890"]
            }
        }
    }
    
    # Crear servidor MCP con autenticación
    server = InstantMCPServer(skill_manager, environment="production", config=config)
    
    print(f"Servidor MCP seguro iniciado en http://localhost:8000/mcp")
    print("Autenticación API Key habilitada")
    print("API Keys válidas: sk_test_12345, sk_live_67890")
    print("Presiona Ctrl+C para detener el servidor")
    
    # Iniciar el servidor
    server.run()

if __name__ == "__main__":
    main()