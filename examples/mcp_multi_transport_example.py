#!/usr/bin/env python3
"""
Ejemplo de InstantMCPServer con múltiples transportes.

Este ejemplo muestra cómo configurar un servidor MCP que utiliza tanto
el transporte HTTP como stdio simultáneamente.

Para ejecutar:
    python examples/mcp_multi_transport_example.py
"""

import time
from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Definir skills
@skill(
    description="Genera un saludo personalizado",
    parameters={
        "name": "Nombre de la persona",
        "formal": "Si el saludo debe ser formal (opcional)"
    }
)
def generate_greeting(name: str, formal: bool = False) -> str:
    """
    Genera un saludo personalizado.
    
    Args:
        name: Nombre de la persona
        formal: Si el saludo debe ser formal
        
    Returns:
        Saludo personalizado
    """
    if formal:
        return f"Estimado/a {name}, es un placer saludarle."
    else:
        return f"¡Hola {name}! ¿Cómo estás?"

@skill(
    description="Formatea una fecha en español",
    parameters={
        "year": "Año",
        "month": "Mes (1-12)",
        "day": "Día (1-31)"
    }
)
def format_date_es(year: int, month: int, day: int) -> str:
    """
    Formatea una fecha en español.
    
    Args:
        year: Año
        month: Mes (1-12)
        day: Día (1-31)
        
    Returns:
        Fecha formateada en español
    """
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    
    # Validar entradas
    if not (1 <= month <= 12):
        raise ValueError("El mes debe estar entre 1 y 12")
    if not (1 <= day <= 31):
        raise ValueError("El día debe estar entre 1 y 31")
    
    return f"{day} de {months[month-1]} de {year}"

def main():
    # Crear y configurar SkillManager
    skill_manager = SkillManager()
    skill_manager.register_skill(generate_greeting)
    skill_manager.register_skill(format_date_es)
    
    #print(f"Skills registradas: {skill_manager.get_skill_names()}")
    
    # Configuración con múltiples transportes
    config = {
        "server_name": "Servidor Multi-Transporte",
        "http": {
            "enabled": True,
            "host": "localhost",
            "port": 8000
        },
        "stdio": {
            "enabled": True  # Habilitar también stdio
        },
        "instructions": """
        Este servidor MCP proporciona herramientas de formato y generación de texto.
        Está disponible tanto a través de HTTP como de stdio.
        
        Herramientas disponibles:
        - generate_greeting: Genera un saludo personalizado
        - format_date_es: Formatea una fecha en español
        """
    }
    
    # Crear servidor MCP con múltiples transportes
    server = InstantMCPServer(skill_manager, config=config)
    
    # Iniciar el servidor
    server.start()
    
    print("Servidor MCP iniciado con múltiples transportes:")
    print(f"- HTTP: http://localhost:8000/mcp")
    print("- stdio: Disponible para integración con Claude")
    print("\nEste servidor puede ser utilizado simultáneamente por:")
    print("- Aplicaciones web a través de HTTP")
    print("- Claude u otros clientes MCP a través de stdio")
    print("\nPresiona Ctrl+C para detener el servidor")
    
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