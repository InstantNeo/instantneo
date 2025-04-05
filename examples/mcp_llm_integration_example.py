#!/usr/bin/env python3
"""
Ejemplo de InstantMCPServer con integración de modelo de lenguaje.

Este ejemplo muestra cómo crear skills que utilizan InstantNeo para
generar texto, resumir contenido y generar código.

Para ejecutar:
    python examples/mcp_llm_integration_example.py

Nota: Necesitas tener configuradas las API keys para InstantNeo.
"""

import time
import os
from instantneo import InstantNeo
from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Verificar si hay API keys configuradas
def check_api_keys():
    """Verifica si las API keys necesarias están configuradas."""
    required_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"]
    missing_keys = [key for key in required_keys if not os.environ.get(key)]
    
    if missing_keys:
        print("ADVERTENCIA: Las siguientes API keys no están configuradas:")
        for key in missing_keys:
            print(f"  - {key}")
        print("\nPuedes configurarlas en el archivo .env o exportarlas como variables de entorno.")
        print("Para este ejemplo, se utilizará un modo simulado si no hay API keys disponibles.")
        return False
    
    return True

# Modo simulado para cuando no hay API keys
def simulated_generate(prompt):
    """Genera texto simulado cuando no hay API keys disponibles."""
    print(f"[Modo simulado] Generando respuesta para: {prompt[:50]}...")
    time.sleep(1)  # Simular tiempo de procesamiento
    
    if "resume" in prompt.lower():
        return "Este es un resumen simulado del texto proporcionado. El contenido ha sido condensado manteniendo los puntos principales."
    elif "código" in prompt.lower() or "code" in prompt.lower():
        lang = "python"
        if "javascript" in prompt.lower() or "js" in prompt.lower():
            lang = "javascript"
        elif "java" in prompt.lower():
            lang = "java"
            
        if lang == "python":
            return "def hello_world():\n    print('Hello, world!')\n\nhello_world()"
        elif lang == "javascript":
            return "function helloWorld() {\n    console.log('Hello, world!');\n}\n\nhelloWorld();"
        else:
            return "public class HelloWorld {\n    public static void main(String[] args) {\n        System.out.println(\"Hello, world!\");\n    }\n}"
    else:
        return "Esta es una respuesta simulada generada para demostrar la funcionalidad. En un entorno real, esto sería generado por un modelo de lenguaje."

# Definir skills que utilizan el modelo de lenguaje
@skill(
    description="Resume un texto",
    parameters={
        "text": "Texto a resumir",
        "max_words": "Número máximo de palabras (opcional)"
    }
)
def summarize_text(text: str, max_words: int = 100) -> str:
    """
    Resume un texto utilizando un modelo de lenguaje.
    
    Args:
        text: Texto a resumir
        max_words: Número máximo de palabras
        
    Returns:
        Resumen del texto
    """
    # Crear instancia de InstantNeo o usar modo simulado
    if check_api_keys():
        instant_neo = InstantNeo()
        prompt = f"""
        Resume el siguiente texto en no más de {max_words} palabras:
        
        {text}
        
        Resumen:
        """
        
        response = instant_neo.generate(prompt)
        return response.strip()
    else:
        return simulated_generate(f"Resume este texto en {max_words} palabras: {text}")

@skill(
    description="Genera código basado en una descripción",
    parameters={
        "description": "Descripción de lo que debe hacer el código",
        "language": "Lenguaje de programación"
    }
)
def generate_code(description: str, language: str) -> str:
    """
    Genera código utilizando un modelo de lenguaje.
    
    Args:
        description: Descripción de lo que debe hacer el código
        language: Lenguaje de programación
        
    Returns:
        Código generado
    """
    # Crear instancia de InstantNeo o usar modo simulado
    if check_api_keys():
        instant_neo = InstantNeo()
        prompt = f"""
        Genera código en {language} que haga lo siguiente:
        
        {description}
        
        ```{language}
        """
        
        response = instant_neo.generate(prompt)
        
        # Extraer solo el código
        if "```" in response:
            parts = response.split("```")
            if len(parts) >= 3:
                return parts[1].replace(f"{language}\n", "", 1)
        
        return response.strip()
    else:
        return simulated_generate(f"Genera código en {language} para: {description}")

@skill(
    description="Responde preguntas sobre un tema",
    parameters={
        "question": "Pregunta a responder",
        "context": "Contexto adicional (opcional)"
    }
)
def answer_question(question: str, context: str = "") -> str:
    """
    Responde preguntas utilizando un modelo de lenguaje.
    
    Args:
        question: Pregunta a responder
        context: Contexto adicional
        
    Returns:
        Respuesta a la pregunta
    """
    # Crear instancia de InstantNeo o usar modo simulado
    if check_api_keys():
        instant_neo = InstantNeo()
        
        prompt = f"""
        Pregunta: {question}
        
        """
        
        if context:
            prompt += f"""
            Contexto adicional:
            {context}
            
            """
            
        prompt += "Respuesta:"
        
        response = instant_neo.generate(prompt)
        return response.strip()
    else:
        return simulated_generate(f"Responde esta pregunta: {question} (Contexto: {context})")

def main():
    # Crear y configurar SkillManager
    skill_manager = SkillManager()
    skill_manager.register_skill(summarize_text)
    skill_manager.register_skill(generate_code)
    skill_manager.register_skill(answer_question)
    
    #print(f"Skills registradas: {skill_manager.get_skill_names()}")
    
    # Verificar API keys
    has_api_keys = check_api_keys()
    mode = "real" if has_api_keys else "simulado"
    
    # Configuración del servidor
    config = {
        "server_name": "InstantNeo AI Server",
        "http": {
            "host": "localhost",
            "port": 8000
        },
        "instructions": f"""
        Este servidor MCP proporciona acceso a capacidades de IA para resumir textos,
        generar código y responder preguntas. Está funcionando en modo {mode}.
        
        Herramientas disponibles:
        - summarize_text: Resume un texto
        - generate_code: Genera código basado en una descripción
        - answer_question: Responde preguntas sobre un tema
        """
    }
    
    # Crear servidor MCP
    server = InstantMCPServer(skill_manager, config=config)
    
    # Iniciar el servidor
    server.start()
    
    print(f"Servidor iniciado en http://localhost:8000/mcp")
    print(f"Modo: {mode.upper()}")
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