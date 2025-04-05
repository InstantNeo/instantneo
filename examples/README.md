# Ejemplos de InstantMCPServer

Este directorio contiene ejemplos de uso de `InstantMCPServer` con `SkillManager` para crear servidores MCP personalizados. Cada ejemplo muestra diferentes configuraciones y casos de uso.

## Requisitos

Para ejecutar estos ejemplos, necesitas tener instalado InstantNeo y sus dependencias:

```bash
pip install -e .  # Instalar InstantNeo en modo desarrollo
pip install fastapi uvicorn  # Dependencias para el transporte HTTP
```

## Ejemplos Disponibles

### 1. Ejemplo Básico

**Archivo**: `mcp_basic_example.py`

Muestra la configuración mínima para crear un servidor MCP con operaciones matemáticas básicas.

```bash
python examples/mcp_basic_example.py
```

### 2. Configuración HTTP Personalizada

**Archivo**: `mcp_custom_http_example.py`

Demuestra cómo personalizar la configuración HTTP, incluyendo host, puerto y CORS.

```bash
python examples/mcp_custom_http_example.py
```

### 3. Autenticación API Key

**Archivo**: `mcp_api_key_auth_example.py`

Muestra cómo configurar la autenticación mediante API Keys para proteger el acceso a las skills.

```bash
python examples/mcp_api_key_auth_example.py
```

### 4. Transporte stdio (para Claude)

**Archivo**: `mcp_stdio_example.py`

Configura un servidor MCP que utiliza el transporte stdio para integración con Claude y otros clientes MCP.

```bash
python examples/mcp_stdio_example.py
```

### 5. HTTPS

**Archivo**: `mcp_https_example.py`

Muestra cómo configurar un servidor MCP con HTTPS para comunicaciones seguras.

```bash
# Primero, genera certificados SSL (solo para desarrollo)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Luego ejecuta el ejemplo
python examples/mcp_https_example.py
```

### 6. Skills Complejas y Manejo de Errores

**Archivo**: `mcp_complex_skills_example.py`

Implementa skills más complejas con manejo de errores adecuado y configuración de logging para depuración.

```bash
python examples/mcp_complex_skills_example.py
```

### 7. Múltiples Transportes

**Archivo**: `mcp_multi_transport_example.py`

Configura un servidor MCP que utiliza tanto el transporte HTTP como stdio simultáneamente.

```bash
python examples/mcp_multi_transport_example.py
```

### 8. Integración con Modelo de Lenguaje

**Archivo**: `mcp_llm_integration_example.py`

Muestra cómo crear skills que utilizan InstantNeo para generar texto, resumir contenido y generar código.

```bash
# Configura tus API keys (requerido para modo real)
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-...
export GROQ_API_KEY=gsk_...

# Ejecuta el ejemplo
python examples/mcp_llm_integration_example.py
```

## Uso con Claude

Para usar estos servidores MCP con Claude:

1. Para servidores con transporte HTTP:
   - Inicia el servidor con uno de los ejemplos
   - Copia la URL del servidor (ej. `http://localhost:8000/mcp`)
   - En Claude, conecta a esta URL como servidor MCP

2. Para servidores con transporte stdio:
   - Usa el comando `mcp install` para instalar el servidor en Claude Desktop:
     ```bash
     mcp install examples/mcp_stdio_example.py
     ```
   - O configura manualmente el archivo `claude_desktop_config.json`

## Notas Importantes

- **Seguridad**: En producción, siempre habilita la autenticación y usa HTTPS.
- **Manejo de errores**: Implementa manejo de errores adecuado en tus skills.
- **Logging**: Configura el logging apropiadamente para facilitar la depuración.
- **Recursos**: Considera el uso de recursos del sistema al implementar skills complejas.
- **Timeout**: Las operaciones largas pueden causar timeouts en los clientes MCP.

## Personalización

Puedes usar estos ejemplos como base para crear tus propios servidores MCP personalizados. Modifica las skills, la configuración y los transportes según tus necesidades.