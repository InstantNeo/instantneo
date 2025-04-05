#!/usr/bin/env python3
"""
Ejemplo de InstantMCPServer con transporte stdio para Claude.

Este ejemplo muestra cómo configurar un servidor MCP que utiliza el transporte stdio,
lo que permite la integración con Claude y otros clientes MCP que soporten este transporte.

Para ejecutar:
    python examples/mcp_stdio_example.py
"""

from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Definir skills
@skill(
    description="Traduce texto al español",
    parameters={
        "text": "Texto a traducir"
    }
)
def translate_to_spanish(text: str) -> str:
    # Implementación simplificada
    translations = {
        "hello": "hola",
        "world": "mundo",
        "thank you": "gracias",
        "goodbye": "adiós",
        "please": "por favor",
        "yes": "sí",
        "no": "no"
    }
    return translations.get(text.lower(), f"[Traducción no disponible para: {text}]")

@skill(
    description="Convierte temperatura de Fahrenheit a Celsius",
    parameters={
        "fahrenheit": "Temperatura en grados Fahrenheit"
    }
)
def fahrenheit_to_celsius(fahrenheit: float) -> float:
    return (fahrenheit - 32) * 5/9

def main():
    # Crear y configurar SkillManager
    skill_manager = SkillManager()
    skill_manager.register_skill(translate_to_spanish)
    skill_manager.register_skill(fahrenheit_to_celsius)
    
    ##print(f"Skills registradas: {skill_manager.get_skill_names()}")
    
    # Configuración para Claude (stdio)
    config = {
        "server_name": "Servidor de Utilidades",
        "http": {
            "enabled": False  # Deshabilitar HTTP
        },
        "stdio": {
            "enabled": True   # Habilitar stdio
        },
        "instructions": """
        Este servidor MCP proporciona herramientas de traducción y conversión.
        
        Herramientas disponibles:
        - translate_to_spanish: Traduce palabras comunes del inglés al español
        - fahrenheit_to_celsius: Convierte temperaturas de Fahrenheit a Celsius
        """
    }
    
    """print("Iniciando servidor MCP con transporte stdio")
    print("Este servidor está diseñado para ser utilizado con Claude u otros clientes MCP")
    print("No verás una URL, ya que la comunicación es a través de stdin/stdout")
    """
    # Crear servidor MCP para Claude
    server = InstantMCPServer(skill_manager, config=config)
    
    # Iniciar el servidor
    server.run()

if __name__ == "__main__":
    main()