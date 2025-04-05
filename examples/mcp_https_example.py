#!/usr/bin/env python3
"""
Ejemplo de InstantMCPServer con HTTPS.

Este ejemplo muestra cómo configurar un servidor MCP con HTTPS para
comunicaciones seguras.

Para ejecutar:
    python examples/mcp_https_example.py

Nota: Antes de ejecutar este ejemplo, debes generar certificados SSL:
    openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
"""

import os
import time
from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Definir skills
@skill(
    description="Verifica una firma digital",
    parameters={
        "data": "Datos a verificar",
        "signature": "Firma a verificar"
    }
)
def verify_signature(data: str, signature: str) -> bool:
    # Implementación simplificada
    return len(data) > 0 and len(signature) > 0

@skill(
    description="Genera un hash de los datos",
    parameters={
        "data": "Datos para generar el hash"
    }
)
def generate_hash(data: str) -> str:
    # Implementación simplificada
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()

def check_certificates():
    """Verifica si existen los certificados SSL o los crea para demostración."""
    cert_path = "cert.pem"
    key_path = "key.pem"
    
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        print("No se encontraron certificados SSL.")
        print("Para un entorno de producción, debes generar certificados válidos con:")
        print("    openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes")
        print("\nPara este ejemplo, se utilizará HTTP en lugar de HTTPS.")
        return False
    
    return True

def main():
    # Crear y configurar SkillManager
    skill_manager = SkillManager()
    skill_manager.register_skill(verify_signature)
    skill_manager.register_skill(generate_hash)
    
    #print(f"Skills registradas: {skill_manager.get_skill_names()}")
    
    # Verificar certificados
    has_certificates = check_certificates()
    
    # Configuración HTTPS
    config = {
        "server_name": "Servidor Seguro HTTPS",
        "http": {
            "host": "localhost",
            "port": 8443,
            "use_https": has_certificates,
            "cert_file": "cert.pem" if has_certificates else None,
            "key_file": "key.pem" if has_certificates else None
        }
    }
    
    # Crear servidor MCP con HTTPS
    server = InstantMCPServer(skill_manager, environment="production", config=config)
    
    # Iniciar el servidor
    server.start()
    
    protocol = "https" if has_certificates else "http"
    print(f"Servidor iniciado en {protocol}://localhost:{config['http']['port']}/mcp")
    if has_certificates:
        print("HTTPS habilitado con certificados SSL")
    else:
        print("Ejecutando en HTTP (sin SSL)")
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