# Guía de Inicio Rápido de InstantNeo

## Instalación

```bash
pip install instantneo
```

## Creando un Agente Simple

Comencemos creando un agente básico sin ningún tool:

```python
from instantneo import InstantNeo

# Crear un agente simple con Claude de Anthropic
agent = InstantNeo(
    provider="anthropic",  # Opciones: "openai", "anthropic", "groq"
    api_key="your_api_key_here",
    model="claude-3-sonnet-20240229",
    role_setup="Eres un asistente útil enfocado en responder preguntas de forma clara y concisa.",
    temperature=0.7,
    max_tokens=500
)

# Usar el agente para una conversación básica
response = agent.run(
    prompt="¿Cuál es la capital de Francia?"
)

print(response)
```

## Creando un Tool Simple

Los tools permiten que tu agente realice funciones específicas. Creemos un tool básico:

```python
from instantneo.skills import tool

@tool(
    description="Sumar dos números y devolver el resultado",
    parameters={
        "a": "Primer número a sumar",
        "b": "Segundo número a sumar"
    },
    tags=["math", "arithmetic"]
)
def add(a: int, b: int) -> int:
    return a + b
```

Nota que:

- El decorador `@tool` agrega metadata a la función
- La información de tipo proviene de los type hints de Python (`: int`)
- Las descripciones de parámetros provienen del diccionario `parameters` en el decorador
- Los docstrings son opcionales - la metadata en el decorador es suficiente

## Agregando Tools a Tu Agente

Ahora agreguemos el tool a nuestro agente:

```python
# Registrar el tool con el agente
agent.register_tool(add)

# Verificar los tools disponibles
print(f"Tools disponibles: {agent.get_tool_names()}")

# Usar el agente con el nuevo tool
response = agent.run(
    prompt="Necesito sumar 42 y 28, ¿cuál es el resultado?"
)

print(response)
```

## Creando Múltiples Tools

Creemos algunos tools más:

```python
@tool(
    description="Verificar si un texto contiene una palabra clave",
    parameters={
        "text": "El texto donde buscar",
        "keyword": "La palabra clave a buscar"
    },
    tags=["text", "search"]
)
def find_keyword(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()

@tool(
    description="Calcular la longitud de un string de texto",
    parameters={
        "text": "El texto de entrada"
    },
    tags=["text", "utility"]
)
def text_length(text: str) -> int:
    return len(text)

# Registrar los nuevos tools
agent.register_tool(find_keyword)
agent.register_tool(text_length)
```

## Controlando Qué Tools Se Usan

Puedes controlar qué tools están disponibles para cada run:

```python
# Usar solo tools específicos para una consulta particular
response = agent.run(
    prompt="¿Cuántos caracteres tiene la palabra 'Python'?",
    skills=["text_length"]  # Solo usar el tool text_length para esta consulta
)

print(response)

# Usar múltiples tools específicos
response = agent.run(
    prompt="¿Está la palabra 'lenguaje' en este texto: 'Python es un lenguaje de programación'?",
    skills=["find_keyword", "text_length"]  # Usar estos dos tools
)
```

## Modos de Ejecución

InstantNeo soporta tres modos de ejecución:

```python
# Esperar la ejecución del tool y devolver resultados (por defecto)
response = agent.run(
    prompt="Suma 5 y 7",
    execution_mode="wait_response"
)

# Ejecutar tools sin esperar resultados
agent.run(
    prompt="Procesa estos datos en segundo plano",
    execution_mode="execution_only"
)

# Solo obtener los argumentos sin ejecutar los tools
args = agent.run(
    prompt="Suma 10 y 20",
    execution_mode="get_args"
)
print(args)  # Mostrará el nombre del tool y los argumentos
```

## Usando AgentCapabilities

Para una gestión de tools más organizada, usa AgentCapabilities:

```python
from instantneo.skills import AgentCapabilities

# Crear capabilities especializados
math_skills = AgentCapabilities()
text_skills = AgentCapabilities()

# Registrar tools en los capabilities apropiados
math_skills.register_tool(add)
text_skills.register_tool(find_keyword)
text_skills.register_tool(text_length)

# Crear agente con tools específicos
agent = InstantNeo(
    provider="openai",
    api_key="your_api_key",
    model="gpt-4",
    role_setup="Eres un asistente útil.",
    skills=math_skills  # Inicializar solo con tools de matemáticas
)

# Más tarde, combinar tools de diferentes capabilities
agent.sm_ops_union(text_skills)

# Comparar conjuntos de tools
comparison = agent.sm_ops_compare(math_skills)
print(comparison)  # Muestra tools comunes y únicos
```

## Cargando Tools Dinámicamente

Carga tools desde archivos o carpetas:

```python
# Cargar desde un archivo específico
agent.load_skills_from_file("./my_skills.py")

# Cargar desde una carpeta entera
agent.load_skills_from_folder("./skills_library")

# Cargar con filtrado
agent.capabilities.load_skills.from_folder(
    "./skills_library",
    by_tags=["math"]  # Solo cargar tools con este tag
)
```

## Streaming de Respuestas

Obtén respuestas en tiempo real:

```python
for chunk in agent.run(
    prompt="Explica el concepto de agentes de IA",
    stream=True
):
    print(chunk, end="", flush=True)
```

## Trabajando con Imágenes (Multimodal)

```python
agent = InstantNeo(
    provider="openai",
    api_key="your_api_key",
    model="gpt-4-vision-preview",
    role_setup="Eres un asistente con capacidad de visión.",
    images=["./default_image.jpg"]  # Imagen por defecto
)

response = agent.run(
    prompt="¿Qué puedes ver en esta imagen?",
    images=["./specific_image.jpg"]  # Override para este run
)
```

## Ejecución Asíncrona

Ejecuta tools en segundo plano:

```python
response = agent.run(
    prompt="Procesa este dataset grande",
    async_execution=True,
    execution_mode="wait_response"
)
```

Para información más detallada, revisa la documentación completa y los ejemplos en la carpeta docs de este repositorio.
