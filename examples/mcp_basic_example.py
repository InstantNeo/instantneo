#!/usr/bin/env python3
"""
Ejemplo básico de InstantMCPServer con configuración mínima.

Este ejemplo muestra cómo crear un servidor MCP simple con operaciones matemáticas básicas.

Para ejecutar:
    python examples/mcp_basic_example.py
"""

from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Definir skills
@skill(description="Suma dos números")
def add(a: float, b: float) -> float:
    return a + b

@skill(description="Resta dos números")
def subtract(a: float, b: float) -> float:
    return a - b

def main():
    # Crear y configurar SkillManager
    skill_manager = SkillManager()
    skill_manager.register_skill(add)
    skill_manager.register_skill(subtract)
    
    #print(f"Skills registradas: {skill_manager.get_skill_names()}")
    
    # Crear servidor MCP con configuración mínima
    server = InstantMCPServer(skill_manager)
    
    print("Servidor MCP iniciado con configuración por defecto")
    print("Presiona Ctrl+C para detener el servidor")
    
    # Iniciar y ejecutar el servidor
    server.run()  # Esto bloqueará el hilo principal

if __name__ == "__main__":
    main()