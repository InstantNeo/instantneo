# Guía del Servidor MCP de InstantNeo

## Introducción

El Servidor MCP (Model Context Protocol) de InstantNeo permite exponer las skills registradas en un `SkillManager` como tools MCP, permitiendo que cualquier cliente compatible con el protocolo MCP pueda descubrirlas y utilizarlas.

Esta funcionalidad facilita la integración de InstantNeo con otros sistemas y herramientas que soporten el protocolo MCP, como asistentes de IA, editores de código y otras aplicaciones.

## Requisitos

Para utilizar el servidor MCP, necesitas:

- InstantNeo instalado
- Para el transporte HTTP: FastAPI y Uvicorn (`pip install fastapi uvicorn`)

## Uso Básico

### Crear un Servidor MCP

```python
from instantneo.skills import SkillManager
from instantneo.mcp import InstantMCPServer

# Crear un SkillManager con skills registradas
skill_manager = SkillManager()
skill_manager.register_skill(mi_skill)

# Crear el servidor MCP
server = InstantMCPServer(skill_manager)

# Iniciar el servidor
server.start()

# Para mantenerlo en ejecución
server.run()  # Esto bloquea hasta que se interrumpa con Ctrl+C
```

### Configuración Personalizada

Puedes personalizar el comportamiento del servidor mediante un diccionario de configuración:

```python
config = {
    "http": {
        "host": "0.0.0.0",  # Escuchar en todas las interfaces
        "port": 8080,        # Puerto personalizado
        "use_https": True,   # Usar HTTPS
        "cert_file": "cert.pem",
        "key_file": "key.pem",
        "cors_origins": ["https://mi-app.com"]  # Restringir CORS
    },
    "stdio": {
        "enabled": True      # Habilitar transporte stdio
    },
    "logging": {
        "level": "debug",    # Nivel de logging
        "file": "mcp.log"    # Archivo de log
    },
    "instructions": "Instrucciones para el cliente MCP sobre cómo usar las tools"
}

server = InstantMCPServer(skill_manager, environment="production", config=config)
```

### Entornos de Ejecución

El servidor soporta tres entornos predefinidos:

- **development**: Configuración para desarrollo local (por defecto)
- **production**: Configuración optimizada para producción
- **testing**: Configuración para pruebas

```python
# Servidor para producción
server = InstantMCPServer(skill_manager, environment="production")
```

## Transportes

### HTTP/HTTPS

El transporte HTTP/HTTPS utiliza FastAPI para exponer un endpoint MCP en `/mcp`. Este endpoint soporta:

- Solicitudes JSON-RPC mediante POST
- Eventos Server-Sent (SSE) mediante GET

Por defecto, el servidor escucha en `http://localhost:8000/mcp`.

### stdio

El transporte stdio permite la comunicación a través de la entrada/salida estándar, siguiendo el formato de líneas delimitadas por saltos de línea del protocolo MCP.

Este transporte es útil para integrar el servidor como un subproceso en otras aplicaciones.

## Seguridad

### HTTPS

Para producción, se recomienda habilitar HTTPS:

```python
config = {
    "http": {
        "use_https": True,
        "cert_file": "ruta/al/certificado.pem",
        "key_file": "ruta/a/clave_privada.pem"
    }
}
```

### Autenticación

El servidor soporta autenticación mediante API keys:

```python
config = {
    "http": {
        "auth": {
            "enabled": True,
            "type": "api_key",
            "api_keys": ["clave-secreta-1", "clave-secreta-2"]
        }
    }
}
```

## Ejemplo Completo

```python
import time
from instantneo.skills import skill, SkillManager
from instantneo.mcp import InstantMCPServer

# Definir una skill
@skill(
    description="Saluda a una persona",
    parameters={"name": "Nombre de la persona"}
)
def greet(name: str) -> str:
    return f"¡Hola, {name}!"

# Crear y configurar el servidor
skill_manager = SkillManager()
skill_manager.register_skill(greet)

config = {
    "http": {
        "port": 8080,
        "cors_origins": ["*"]
    }
}

server = InstantMCPServer(skill_manager, config=config)
server.start()

print("Servidor MCP iniciado en http://localhost:8080/mcp")
print("Presiona Ctrl+C para detener")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    server.stop()
    print("Servidor detenido")
```

## Integración con Clientes MCP

Los clientes MCP pueden conectarse al servidor utilizando el endpoint HTTP o el transporte stdio, según corresponda.

### Ejemplo de Solicitud JSON-RPC

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
```

### Ejemplo de Respuesta

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "greet",
        "description": "Saluda a una persona",
        "inputSchema": {
          "type": "object",
          "properties": {
            "name": {
              "type": "string",
              "description": "Nombre de la persona"
            }
          },
          "required": ["name"]
        }
      }
    ]
  }
}
```

## Extensibilidad

El servidor MCP está diseñado para ser extensible. En futuras versiones, se añadirá soporte para:

- Recursos MCP
- Prompts MCP
- Autenticación OAuth
- Más transportes

## Solución de Problemas

### El servidor no inicia

Verifica:
- Que los puertos no estén en uso
- Que tengas los permisos necesarios
- Que las dependencias estén instaladas

### Errores de conexión

- Verifica la configuración de CORS si estás conectando desde un navegador
- Asegúrate de que el firewall permita conexiones al puerto configurado
- Verifica la configuración de SSL si estás usando HTTPS

### Logs

Habilita el logging en modo debug para obtener más información:

```python
config = {
    "logging": {
        "level": "debug"
    }
}
```

## Referencia de API

Consulta la documentación de referencia de la API para obtener información detallada sobre todas las opciones de configuración y métodos disponibles.