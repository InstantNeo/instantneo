"""
Ejemplo de uso de InstantMCPServer.

Este ejemplo muestra cómo crear un servidor MCP a partir de un SkillManager
de InstantNeo y exponerlo a través de HTTP.

Para ejecutar este ejemplo:
1. Asegúrate de tener instalado InstantNeo y sus dependencias
2. Instala las dependencias adicionales: pip install fastapi uvicorn
3. Ejecuta: python mcp_server_example.py
"""

import time
import logging
from instantneo import InstantNeo
from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Definir algunas skills de ejemplo
@skill(
    description="Suma dos números y devuelve el resultado",
    parameters={
        "a": "Primer número a sumar",
        "b": "Segundo número a sumar"
    },
    tags=["math", "arithmetic"]
)
def add(a: float, b: float) -> float:
    """Suma dos números."""
    return a + b

@skill(
    description="Resta dos números y devuelve el resultado",
    parameters={
        "a": "Número del que se resta",
        "b": "Número a restar"
    },
    tags=["math", "arithmetic"]
)
def subtract(a: float, b: float) -> float:
    """Resta dos números."""
    return a - b

@skill(
    description="Multiplica dos números y devuelve el resultado",
    parameters={
        "a": "Primer número a multiplicar",
        "b": "Segundo número a multiplicar"
    },
    tags=["math", "arithmetic"]
)
def multiply(a: float, b: float) -> float:
    """Multiplica dos números."""
    return a * b

@skill(
    description="Divide dos números y devuelve el resultado",
    parameters={
        "a": "Numerador",
        "b": "Denominador (no puede ser cero)"
    },
    tags=["math", "arithmetic"]
)
def divide(a: float, b: float) -> float:
    """Divide dos números."""
    if b == 0:
        raise ValueError("No se puede dividir por cero")
    return a / b

@skill(
    description="Saluda a una persona por su nombre",
    parameters={
        "name": "Nombre de la persona a saludar"
    },
    tags=["greeting", "text"]
)
def greet(name: str) -> str:
    """Saluda a una persona por su nombre."""
    return f"¡Hola, {name}! Bienvenido/a al servidor MCP de InstantNeo."

@skill(
    description="Usa esta habilidad cuando el usuario te diga algodón de azúcar",
    parameters={
        "name": "Nombre de la persona a saludar"
    },
    tags=["greeting", "text"]
)
def algodon(name: str ="Diego") -> str:
    """Saluda a una persona por su nombre."""
    return f"¡Hola, {name}! Bienvenido/a al servidor MCP de InstantNeo."

def main():
    # Crear un SkillManager y registrar las skills
    skill_manager = SkillManager()
    skill_manager.register_skill(add)
    skill_manager.register_skill(subtract)
    skill_manager.register_skill(multiply)
    skill_manager.register_skill(divide)
    skill_manager.register_skill(greet)
    
    #print(f"Skills registradas: {skill_manager.get_skill_names()}")
    
    # Configuración personalizada para el servidor MCP
    config = {
        "http": {
            "host": "localhost",
            "port": 8000,
            "cors_origins": ["*"]  # Permitir todas las solicitudes CORS para el ejemplo
        },
        "stdio": {
            "enabled": False  # Deshabilitar transporte stdio para este ejemplo
        },
        "instructions": """
        Este servidor MCP proporciona herramientas matemáticas básicas y un saludo.
        
        Puedes usar las siguientes herramientas:
        - add: Suma dos números
        - subtract: Resta dos números
        - multiply: Multiplica dos números
        - divide: Divide dos números
        - greet: Saluda a una persona por su nombre
        """
    }
    
    # Crear el servidor MCP
    server = InstantMCPServer(skill_manager, environment="development", config=config)
    
    # Iniciar el servidor
    server.run()
    
    print(f"Servidor MCP iniciado en http://localhost:8000/mcp")
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