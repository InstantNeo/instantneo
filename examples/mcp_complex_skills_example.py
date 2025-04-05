#!/usr/bin/env python3
"""
Ejemplo de InstantMCPServer con skills complejas y manejo de errores.

Este ejemplo muestra cómo implementar skills más complejas con manejo de errores
adecuado y cómo configurar el logging para depuración.

Para ejecutar:
    python examples/mcp_complex_skills_example.py
"""

import time
import json
import logging
from typing import Dict, List, Any
from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Configurar logging básico
logging.basicConfig(level=logging.INFO)

# Definir skills complejas
@skill(
    description="Analiza un texto y extrae entidades",
    parameters={
        "text": "Texto a analizar"
    }
)
def extract_entities(text: str) -> Dict[str, List[str]]:
    """
    Extrae entidades de un texto utilizando reglas simples.
    
    Args:
        text: Texto a analizar
        
    Returns:
        Diccionario con listas de entidades por categoría
    """
    logging.debug(f"Analizando texto: {text[:50]}...")
    
    # Implementación simplificada de NER
    entities = {
        "personas": [],
        "lugares": [],
        "organizaciones": []
    }
    
    # Lógica simple de extracción
    words = text.split()
    for word in words:
        if word.istitle():
            if len(word) > 8:
                entities["organizaciones"].append(word)
            elif word.endswith("a") or word.endswith("o"):
                entities["personas"].append(word)
            else:
                entities["lugares"].append(word)
    
    logging.debug(f"Entidades encontradas: {json.dumps(entities)}")
    return entities

@skill(
    description="Procesa una transacción financiera",
    parameters={
        "amount": "Monto de la transacción",
        "currency": "Moneda (USD, EUR, GBP)",
        "description": "Descripción de la transacción"
    }
)
def process_transaction(amount: float, currency: str, description: str) -> Dict[str, Any]:
    """
    Procesa una transacción financiera con validación de entrada.
    
    Args:
        amount: Monto de la transacción
        currency: Moneda (USD, EUR, GBP)
        description: Descripción de la transacción
        
    Returns:
        Información de la transacción procesada
        
    Raises:
        ValueError: Si los parámetros de entrada son inválidos
    """
    logging.info(f"Procesando transacción: {amount} {currency} - {description}")
    
    # Validación de entrada
    if amount <= 0:
        logging.error(f"Monto inválido: {amount}")
        raise ValueError("El monto debe ser positivo")
    
    if currency not in ["USD", "EUR", "GBP"]:
        logging.error(f"Moneda no soportada: {currency}")
        raise ValueError(f"Moneda no soportada: {currency}. Use USD, EUR o GBP.")
    
    # Procesar transacción
    transaction_id = f"TX-{hash(f'{amount}-{currency}-{description}') % 10000:04d}"
    
    # Simular procesamiento
    time.sleep(0.5)
    
    result = {
        "transaction_id": transaction_id,
        "status": "completed",
        "amount": amount,
        "currency": currency,
        "description": description,
        "fee": amount * 0.025,  # 2.5% de comisión
        "timestamp": time.time()
    }
    
    logging.info(f"Transacción completada: {transaction_id}")
    return result

@skill(
    description="Analiza sentimiento de un texto",
    parameters={
        "text": "Texto a analizar"
    }
)
def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    Analiza el sentimiento de un texto.
    
    Args:
        text: Texto a analizar
        
    Returns:
        Análisis de sentimiento
    """
    logging.debug(f"Analizando sentimiento: {text[:50]}...")
    
    # Palabras positivas y negativas para análisis simple
    positive_words = ["bueno", "excelente", "genial", "feliz", "alegre", "increíble", "maravilloso"]
    negative_words = ["malo", "terrible", "horrible", "triste", "enojado", "pésimo", "desagradable"]
    
    # Contar ocurrencias
    text_lower = text.lower()
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    # Determinar sentimiento
    if positive_count > negative_count:
        sentiment = "positivo"
        score = min(1.0, 0.5 + (positive_count - negative_count) * 0.1)
    elif negative_count > positive_count:
        sentiment = "negativo"
        score = max(-1.0, -0.5 - (negative_count - positive_count) * 0.1)
    else:
        sentiment = "neutral"
        score = 0.0
    
    result = {
        "sentiment": sentiment,
        "score": score,
        "positive_words": positive_count,
        "negative_words": negative_count,
        "text_length": len(text)
    }
    
    logging.debug(f"Resultado del análisis: {sentiment} ({score})")
    return result

def main():
    # Crear y configurar SkillManager
    skill_manager = SkillManager()
    skill_manager.register_skill(extract_entities)
    skill_manager.register_skill(process_transaction)
    skill_manager.register_skill(analyze_sentiment)
    
    #print(f"Skills registradas: {skill_manager.get_skill_names()}")
    
    # Configuración con logging detallado
    config = {
        "server_name": "Servidor de Análisis Avanzado",
        "logging": {
            "level": "debug",
            "file": "mcp_server.log"
        },
        "http": {
            "host": "localhost",
            "port": 8000
        },
        "instructions": """
        Este servidor MCP proporciona herramientas para procesamiento de texto y transacciones.
        
        Herramientas disponibles:
        - extract_entities: Analiza un texto y extrae entidades (personas, lugares, organizaciones)
        - process_transaction: Procesa una transacción financiera
        - analyze_sentiment: Analiza el sentimiento de un texto
        """
    }
    
    # Crear servidor MCP
    server = InstantMCPServer(skill_manager, config=config)
    
    print(f"Servidor iniciado en http://localhost:8000/mcp")
    print("Logging detallado habilitado en mcp_server.log")
    print("Presiona Ctrl+C para detener el servidor")
    
    # Iniciar el servidor
    server.run()

if __name__ == "__main__":
    main()