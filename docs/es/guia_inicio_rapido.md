# Guía de Inicio Rápido de InstantNeo

## Instalación

```bash
pip install instantneo
```

## Creando un Agente Simple

Comencemos creando un agente básico sin ninguna skill:

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

## Creando una Skill Simple

Las skills permiten que tu agente realice funciones específicas. Creemos una skill básica:

```python
from instantneo.skills import skill

@skill(
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

- El decorador `@skill` agrega metadata a la función
- La información de tipo proviene de los type hints de Python (`: int`)
- Las descripciones de parámetros provienen del diccionario `parameters` en el decorador
- Los docstrings son opcionales - la metadata en el decorador es suficiente

## Agregando Skills a Tu Agente

Ahora agreguemos la skill a nuestro agente:

```python
# Registrar la skill con el agente
agent.register_skill(add)

# Verificar las skills disponibles
print(f"Skills disponibles: {agent.get_skill_names()}")

# Usar el agente con la nueva skill
response = agent.run(
    prompt="Necesito sumar 42 y 28, ¿cuál es el resultado?"
)

print(response)
```

## Creando Múltiples Skills

Creemos algunas skills más:

```python
@skill(
    description="Verificar si un texto contiene una palabra clave",
    parameters={
        "text": "El texto donde buscar",
        "keyword": "La palabra clave a buscar"
    },
    tags=["text", "search"]
)
def find_keyword(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()

@skill(
    description="Calcular la longitud de un string de texto",
    parameters={
        "text": "El texto de entrada"
    },
    tags=["text", "utility"]
)
def text_length(text: str) -> int:
    return len(text)

# Registrar las nuevas skills
agent.register_skill(find_keyword)
agent.register_skill(text_length)
```

## Controlando Qué Skills Se Usan

Puedes controlar qué skills están disponibles para cada run:

```python
# Usar solo skills específicas para una consulta particular
response = agent.run(
    prompt="¿Cuántos caracteres tiene la palabra 'Python'?",
    skills=["text_length"]  # Solo usar la skill text_length para esta consulta
)

print(response)

# Usar múltiples skills específicas
response = agent.run(
    prompt="¿Está la palabra 'lenguaje' en este texto: 'Python es un lenguaje de programación'?",
    skills=["find_keyword", "text_length"]  # Usar estas dos skills
)
```

## Modos de Ejecución

InstantNeo soporta tres modos de ejecución:

```python
# Esperar la ejecución de la skill y devolver resultados (por defecto)
response = agent.run(
    prompt="Suma 5 y 7",
    execution_mode="wait_response"
)

# Ejecutar skills sin esperar resultados
agent.run(
    prompt="Procesa estos datos en segundo plano",
    execution_mode="execution_only"
)

# Solo obtener los argumentos sin ejecutar las skills
args = agent.run(
    prompt="Suma 10 y 20",
    execution_mode="get_args"
)
print(args)  # Mostrará el nombre de la skill y los argumentos
```

## Usando SkillManager

Para una gestión de skills más organizada, usa SkillManager:

```python
from instantneo.skills import SkillManager

# Crear skill managers especializados
math_skills = SkillManager()
text_skills = SkillManager()

# Registrar skills en los managers apropiados
math_skills.register_skill(add)
text_skills.register_skill(find_keyword)
text_skills.register_skill(text_length)

# Crear agente con skills específicas
agent = InstantNeo(
    provider="openai",
    api_key="your_api_key",
    model="gpt-4",
    role_setup="Eres un asistente útil.",
    skills=math_skills  # Inicializar solo con skills de matemáticas
)

# Más tarde, combinar skills de diferentes managers
agent.sm_ops_union(text_skills)

# Comparar conjuntos de skills
comparison = agent.sm_ops_compare(math_skills)
print(comparison)  # Muestra skills comunes y únicas
```

## Cargando Skills Dinámicamente

Carga skills desde archivos o carpetas:

```python
# Cargar desde un archivo específico
agent.load_skills_from_file("./my_skills.py")

# Cargar desde una carpeta entera
agent.load_skills_from_folder("./skills_library")

# Cargar con filtrado
agent.skill_manager.load_skills.from_folder(
    "./skills_library", 
    by_tags=["math"]  # Solo cargar skills con este tag
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

Ejecuta skills en segundo plano:

```python
response = agent.run(
    prompt="Procesa este dataset grande",
    async_execution=True,
    execution_mode="wait_response"
)
```

Para información más detallada, revisa la documentación completa y los ejemplos en la carpeta docs de este repositorio.