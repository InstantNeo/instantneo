# Referencia Principal de InstantNeo

## Conceptos Fundamentales

InstantNeo proporciona una interfaz unificada para crear agentes de IA que pueden interactuar con varios proveedores de Modelos de Lenguaje Grandes (LLM). La librería está diseñada alrededor de algunos conceptos clave:

### Arquitectura del Agente

Un agente de InstantNeo consiste en:

1. **Configuración Base**: Definida cuando creas una instancia, incluyendo el proveedor del LLM, modelo, prompt del sistema y otros parámetros por defecto.
2. **Registro de Skills**: Funciones que el agente puede ejecutar para realizar tareas específicas.
3. **Motor de Ejecución**: Maneja la comunicación con el LLM y ejecuta skills según sea necesario.

### Relación entre Instancia y Run

La clave para entender InstantNeo es la relación entre la **creación de Instancia** y la **ejecución del método Run**

Piensa en la instancia como la **definición de la identidad y capacidades generales de un agente**, mientras que cada llamada a `run()` representa una **tarea o consulta específica al agente**, con configuraciones especializadas opcionales.

## Creando una Instancia de InstantNeo

### Constructor

```python
InstantNeo(
    provider: str,
    api_key: str,
    model: str,
    role_setup: str,
    skills: Optional[Union[List[str], SkillManager]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = 200,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    stop: Optional[Union[str, List[str]]] = None,
    logit_bias: Optional[Dict[int, float]] = None,
    seed: Optional[int] = None,
    stream: bool = False,
    images: Optional[Union[str, List[str]]] = None,
    image_detail: str = "auto"
)
```

### Parámetros Clave

- **provider**: Selecciona el proveedor del LLM. Opciones: "openai", "anthropic", "groq"
- **api_key**: Tu API key para el proveedor seleccionado
- **model**: El modelo específico a usar (ej., "gpt-4o", "claude-3-opus-20240229")
- **role_setup**: El prompt del sistema que define la personalidad e instrucciones de tu agente
- **skills**: Skills opcionales para hacer disponibles al agente desde el inicio
- **temperature**: Controla la aleatoriedad en las respuestas (mayor = más creativo, menor = más determinista)
- **max_tokens**: Longitud máxima de la respuesta
- **images**: Imágenes por defecto para incluir con los prompts (para modelos multimodales)

Crear una instancia de InstantNeo te da varias ventajas:

1. **Reutilización del Agente**: Configuras al agente una vez, y lo usa muchas veces con diferentes prompts según tareas
2. **Identidad Consistente**: Mantén un rol y comportamiento consistente a través de las interacciones
3. **Gestión de Skills**: Registra skills una vez y úsalas en múltiples ejecuciones
4. **Configuraciones por Defecto**: Establece valores por defecto razonables para los parámetros del modelo

### Ejemplo: Creando Diferentes Tipos de Agentes

```python
# Creando un asistente de programación
coding_assistant = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="""Eres un asistente de programación en Python. 
    Ayudas a escribir código limpio, eficiente y bien documentado.
    Explicas tu razonamiento y sugieres mejoras.""",
    temperature=0.2,  # Temperatura más baja para programación más precisa
    max_tokens=4000   # Respuestas más largas para código detallado
)

# Creando un asistente de escritura creativa
creative_assistant = InstantNeo(
    provider="openai",
    api_key="your-api-key",
    model="gpt-4",
    role_setup="""Eres un asistente de escritura creativa.
    Ayudas a generar ideas, desarrollar personajes y crear prosa atractiva.
    Tu tono es imaginativo y entusiasta.""",
    temperature=0.8,  # Temperatura más alta para respuestas más creativas
    max_tokens=1000
)

# Creando un asistente de investigación multimodal
research_assistant = InstantNeo(
    provider="openai",
    api_key="your-api-key",
    model="gpt-4-vision-preview",
    role_setup="""Eres un asistente de investigación que puede analizar documentos e imágenes.
    Ayudas a extraer información clave, resumir contenido y proporcionar insights.""",
    temperature=0.3,
    max_tokens=2000
)
```

## El Método Run: Núcleo de la Funcionalidad de InstantNeo

El método `run()` es donde ocurre la mayor parte de la acción en InstantNeo. Es a través de este método que interactúas con el agente, proporcionas prompts y obtienes respuestas.

### Firma del Método

```python
run(
    prompt: str,
    execution_mode: str = "wait_response",
    async_execution: bool = False,
    return_full_response: bool = False,
    skills: Optional[List[str]] = None,
    images: Optional[Union[str, List[str]]] = None,
    image_detail: Optional[str] = None,
    stream: bool = False,
    **additional_params
) -> Any
```

### Entendiendo el Método Run

Cuando llamas a `run()`, ocurren varias cosas importantes:

1. **Resolución de Parámetros**:
   - El método primero toma los parámetros por defecto de la instancia
   - Luego aplica cualquier override que hayas especificado en la llamada a `run()`
   - Esto permite flexibilidad mientras se mantienen valores por defecto consistentes

2. **Selección de Skills**:
   - Si especificas `skills` en `run()`, solo esos skills están disponibles para este run específico
   - Si no, todos los skills registrados con el agente están disponibles
   - Esto te permite controlar exactamente qué capacidades están disponibles para cada run

3. **Preparación del Mensaje**:
   - El prompt del sistema (role_setup) se envía al modelo con tu prompt
   - Cualquier imagen se procesa y se agrega al mensaje
   - Los skills se formatean para que el LLM los entienda

4. **Interacción con el LLM**:
   - El mensaje preparado se envía al proveedor del LLM apropiado
   - Las respuestas se procesan según el modo de ejecución
   - Los resultados se devuelven en el formato solicitado

### ¿Por Qué Ajustar Parámetros en Runtime?

La capacidad de sobreescribir parámetros en tiempo de ejecución le da a InstantNeo una flexibilidad excepcional:

1. **Configuraciones Específicas por Tarea**: Ajusta temperature, tokens, etc. según la tarea específica
2. **Uso Selectivo de Skills**: Solo expone los skills necesarios para una consulta específica
3. **Contenido Dinámico**: Incluye diferentes imágenes o contexto adicional según sea necesario
4. **Control de Ejecución**: Elige cómo se ejecutan los skills según el caso de uso

### Parámetros Clave de Run

- **prompt**: Es el input. La instrucción, entrada o consulta.
- **execution_mode**: Define cómo deben ejecutarse las skills (`wait_response`, `execution_only`, o `get_args`)
- **async_execution**: Determina si las skills se deben ejecutar de forma asíncrona
- **skills**: Lista de nombres de skills para hacer disponibles en este run (sobreescribe los defaults de la instancia)
- **images**: Imágenes para incluir con este prompt específico
- **stream**: Indica si se transmitirá la respuesta en chunks

### Ejemplos de Uso del Método Run

#### Uso Básico

```python
# Conversación simple
response = agent.run("¿Cuál es la capital de Francia?")
print(response)

# Con skills específicos habilitados
response = agent.run(
    prompt="¿Cuánto es 125 + 437?",
    skills=["add"]  # Solo hacer disponible el skill add
)
```

#### Sobreescribiendo Parámetros para Tareas Específicas

```python
# Parámetros por defecto para la mayoría de las interacciones
agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="Eres un asistente útil.",
    temperature=0.7,
    max_tokens=500
)

# Override para tareas creativas
creative_response = agent.run(
    prompt="Escribe una historia corta sobre un robot que descubre emociones",
    temperature=0.9,  # Temperature más alta para más creatividad
    max_tokens=2000   # Respuesta más larga para la historia
)

# Override para tareas precisas
precise_response = agent.run(
    prompt="Explica la diferencia entre precision y recall en machine learning",
    temperature=0.2,  # Temperature más baja para explicación más precisa
)
```

#### Trabajando con Imágenes

```python
# Instancia sin imágenes por defecto
agent = InstantNeo(
    provider="openai",
    api_key="your-api-key",
    model="gpt-4-vision-preview",
    role_setup="Eres un asistente de análisis visual."
)

# Analizar una sola imagen
image_response = agent.run(
    prompt="¿Qué puedes ver en esta imagen?",
    images=["./photo.jpg"],
    image_detail="high"  # Solicitar análisis de alto detalle
)

# Comparar múltiples imágenes
comparison_response = agent.run(
    prompt="¿Qué diferencias hay entre estos dos diagramas?",
    images=["./diagram1.jpg", "./diagram2.jpg"]
)

# Proporcionar contexto textual y visual juntos
context_response = agent.run(
    prompt="""Este es un screenshot de un mensaje de error que estoy recibiendo.
    ¿Qué podría estar causándolo y cómo puedo arreglarlo?""",
    images=["./error_screenshot.png"]
)
```

#### Diferentes Modos de Ejecución

```python
# Esperar respuesta (por defecto) - bloquea hasta que la ejecución del skill se completa
result = agent.run(
    prompt="Calcula el área de un círculo con radio 5",
    skills=["circle_area"],
    execution_mode="wait_response"
)
print(f"El área es: {result}")

# Ejecutar sin esperar - dispara el skill y continúa inmediatamente
agent.run(
    prompt="Registra esta actividad de usuario en la base de datos",
    skills=["log_activity"],
    execution_mode="execution_only"
)
print("Registro solicitado (continuando inmediatamente)")

# Obtener argumentos sin ejecutar - útil para validación o manejo personalizado
args = agent.run(
    prompt="Envía un email a john@example.com con asunto 'Reunión Mañana'",
    skills=["send_email"],
    execution_mode="get_args"
)
print(f"Llamaría a la función: {args[0]['name']}")
print(f"Con argumentos: {args[0]['arguments']}")
```

#### Streaming de Respuestas

```python
# Transmitir la respuesta en tiempo real
for chunk in agent.run(
    prompt="Explica la computación cuántica en términos simples",
    stream=True
):
    print(chunk, end="", flush=True)
```

## Otros Métodos Clave en InstantNeo

InstantNeo proporciona varios otros métodos importantes además de `run()`. Aquí hay un resumen breve de los más comúnmente usados:

### Modificando el Comportamiento del Agente

#### mod_role

Cambia el prompt del sistema del agente (role setup).

```python
agent.mod_role("Ahora eres un tutor de matemáticas enfocado en explicar conceptos de forma simple.")
```

**Utilidad**: Te permite reutilizar un agente existente para un rol diferente sin crear una nueva instancia.

### Gestión de Skills

Estos métodos ayudan a gestionar los skills disponibles para el agente. Una guía más detallada sobre skills se proporcionará por separado.

#### register_skill

Agrega un skill a los skills disponibles del agente.

```python
from instantneo.skills import skill

@skill(
    description="Calcular el área de un círculo",
    parameters={"radius": "El radio del círculo"}
)
def circle_area(radius: float) -> float:
    import math
    return math.pi * radius**2

agent.register_skill(circle_area)
```

**Utilidad**: Expande las capacidades del agente con nuevas funciones que puede ejecutar.

#### get_skill_names

Lista todos los nombres de skills registrados.

```python
available_skills = agent.get_skill_names()
print(f"Skills disponibles: {available_skills}")
```

**Utilidad**: Útil para debugging o seleccionar dinámicamente skills a usar en un run.

#### load_skills_from_file, load_skills_from_folder

Carga skills desde archivos Python externos o carpetas.

```python
# Cargar desde un archivo específico
agent.load_skills_from_file("./math_skills.py")

# Cargar desde una carpeta entera
agent.load_skills_from_folder("./skills_library")
```

**Utilidad**: Permite organización modular de skills y cargarlos según sea necesario.

### Operaciones del Skill Manager

Estos métodos proporcionan operaciones de conjuntos para gestionar colecciones de skills. Se cubrirán con más detalle en la guía dedicada a skills.

```python
# Combinar skills de otro agente
agent1.sm_ops_union(agent2)

# Mantener solo skills que existen en ambos agentes
agent1.sm_ops_intersection(agent2)

# Comparar conjuntos de skills
comparison = agent1.sm_ops_compare(agent2)
```

**Utilidad**: Permite gestión sofisticada de colecciones de skills entre agentes.