# Guía de Tools de InstantNeo

## Introducción a los Tools

Los tools son los bloques de construcción fundamentales de capacidades en InstantNeo que empoderan a tus agentes LLM para realizar funciones específicas. Representan una abstracción poderosa construida sobre la capacidad de "function calling" o "tool use" de los modelos de lenguaje modernos.

### ¿Qué Son los Tools?

Los tools en InstantNeo son funciones de Python decoradas con metadata que:

1. Definen su propósito (descripción)
2. Especifican sus parámetros y tipos
3. Categorizan funcionalidad (vía tags)

Cuando un agente LLM encuentra una tarea que coincide con el propósito de un tool, puede invocar ese tool a través de sus capacidades de uso de herramientas, pasando los argumentos apropiados para realizar tareas que de otra manera podrían estar más allá de las capacidades del modelo.

### Relación con Function Calling

Los tools son la implementación de InstantNeo de la capacidad de function calling/tool use que proveedores como OpenAI, Anthropic y otros han introducido. Estas capacidades permiten a los LLMs:

1. Reconocer cuándo un tool o función específica debe usarse
2. Generar los parámetros correctos para llamar esa función
3. Integrar los resultados de vuelta en sus respuestas

El sistema de tools de InstantNeo expande este concepto con características adicionales:

- Interfaz consistente a través de diferentes proveedores de LLM
- Metadata rica para mejor descubrimiento y uso de tools por parte de los LLM
- Control de ejecución
- Herramientas de composición y organización de tools con AgentCapabilities

InstantNeo hace que la gestión de herramientas sea simple y clara, para atender las necesidades de manejo del contexto en el desarrollo de sistemas de agentes.

### El Propósito Principal de los Tools

Los tools extienden las capacidades de tu agente más allá de la generación de texto. Por ejemplo, podrían incluir capacidades para:

- **Realizar cálculos**: Operaciones matemáticas, conversiones, estadísticas
- **Acceder sistemas externos**: Bases de datos, APIs, sistemas de archivos
- **Procesar datos**: Transformaciones, filtrado, análisis
- **Interactuar con herramientas**: Búsquedas web, generación de imágenes, notificaciones
- **Lógica de negocio personalizada**: Algoritmos y workflows específicos del dominio

## El Decorador @tool

El corazón del sistema de tools de InstantNeo es el decorador `@tool`, que transforma funciones regulares de Python en capacidades que los agentes LLM pueden descubrir y usar.

### Qué Hace el Decorador

Cuando aplicas `@tool` a una función:

1. **Captura metadata**: Almacena la descripción, info de parámetros y tags. Si la metadata no es provista, buscará el docstring de la función.
2. **Extrae información de tipo**: Usa los type hints de Python para identificar tipos de parámetros
3. **Crea tracking de ejecución**: Agrega funcionalidad para monitorear llamadas y resultados
4. **Formatea para LLMs**: Prepara la función para ser descubierta por modelos de lenguaje, según el formato para declarar herramientas.

### Sintaxis del Decorador

```python
@tool(
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    tags: Optional[List[str]] = None,
    version: Optional[str] = "1.0",
    **additional_metadata
)
```

## Creando Tools

Examinemos cómo crear tools efectivos para tus agentes de InstantNeo.

### Creación Básica de Tools

El tool más simple requiere solo una función con el decorador `@tool`:

```python
from instantneo.skills import tool

@tool(
    description="Sumar dos números y devolver el resultado"
)
def add(a: int, b: int) -> int:
    return a + b
```

### Metadata Requerida y Opcional

Técnicamente, el único parámetro requerido es la función misma. Sin embargo, para un uso efectivo de los tools:

- **description**: Altamente recomendado para ayudar al LLM a entender cuándo usar el tool, y cómo aprovecharlo correctamente
- **parameters**: Opcional pero recomendado para mejores descripciones de parámetros, especialmente en casos en los que se necesita guiar más al modelo o parámetros complejos.
- **tags**: Opcional pero útil para organizar y filtrar tools
- **version**: Opcional para trackear cambios (por defecto "1.0")

### La Importancia de Buenas Descripciones

Una descripción bien elaborada es crucial para el uso apropiado del tool:

```python
@tool(
    description="Calcular la distancia entre dos coordenadas geográficas usando la fórmula de Haversine, devolviendo el resultado en kilómetros"
)
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Implementación...
```

### Descripciones de Parámetros

Aunque no son obligatorias, las descripciones de parámetros ayudan mucho al LLM a entender qué argumentos proporcionar:

```python
@tool(
    description="Enviar una notificación por email",
    parameters={
        "recipient": "Dirección de email del destinatario",
        "subject": "Línea de asunto del email",
        "body": "Contenido principal del email",
        "priority": "Nivel de importancia (low, normal, high)"
    }
)
def send_email(recipient: str, subject: str, body: str, priority: str = "normal") -> bool:
    # Implementación...
```

Nota que las descripciones de parámetros no incluyen información de tipo - eso viene de los typehints de la función.

### Type Hints: Esenciales para los Tools

Los type hints son cruciales en los tools ya que **le dicen al LLM qué tipos de datos proporcionar como argumentos**

```python
@tool(
    description="Filtrar una lista para mantener solo valores dentro de un rango especificado"
)
def filter_range(values: List[float], min_value: float, max_value: float) -> List[float]:
    return [v for v in values if min_value <= v <= max_value]
```

### Ejemplo Completo de Tool

Aquí hay un tool completo y bien diseñado:

```python
@tool(
    description="Calcular el monto de pago mensual de un préstamo",
    parameters={
        "principal": "Monto total del préstamo en dólares",
        "annual_rate": "Tasa de interés anual (como decimal, ej., 0.05 para 5%)",
        "years": "Plazo del préstamo en años",
    },
    tags=["finance", "loans", "calculation"]
)
def calculate_monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    monthly_rate = annual_rate / 12
    num_payments = years * 12
    if monthly_rate == 0:
        return principal / num_payments
    return principal * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
```

### Ventajas de los Tools de InstantNeo

1. **Simplicidad**: Escribe funciones regulares de Python con metadata adicional
2. **No se requieren docstrings**: La metadata se proporciona directamente en el decorador
3. **Type safety**: Los type hints aseguran tipos de argumentos correctos
4. **Descubribilidad**: La metadata ayuda a los LLMs a encontrar y usar el tool correcto, y a usarlo adecuadamente.
5. **Reutilización**: Los tools pueden compartirse entre diferentes agentes

## AgentCapabilities

AgentCapabilities es un sistema de registro que organiza y gestiona tools para uso de los agentes de InstantNeo.

### Propósito de AgentCapabilities

AgentCapabilities:

1. Proporciona un registro centralizado para los tools
2. Maneja el registro y descubrimiento de tools
3. Gestiona la metadata de los tools
4. Resuelve potenciales conflictos de nombres
5. Permite organización a través de tags
6. Facilita la carga dinámica de tools

### Creando y Usando AgentCapabilities

```python
from instantneo.skills import AgentCapabilities, tool

# Crear un AgentCapabilities
manager = AgentCapabilities()

@tool(description="Calcular el cuadrado de un número")
def square(x: float) -> float:
    return x * x

# Registrar el tool
manager.register_tool(square)

# Usar el manager con un agente de InstantNeo
from instantneo import InstantNeo

agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="Eres un asistente útil.",
    skills=manager  # Pasar el manager completo
)
```

### Métodos Clave de AgentCapabilities

#### register_tool

Agrega un tool al registro.

```python
manager.register_tool(my_function)
```

#### get_tool_names

Devuelve una lista de todos los nombres de tools registrados.

```python
tool_names = manager.get_tool_names()
print(f"Tools disponibles: {tool_names}")
```

#### get_tool_by_name

Recupera una función tool por su nombre.

```python
calculation_tool = manager.get_tool_by_name("calculate_tax")
if calculation_tool:
    result = calculation_tool(amount=100, rate=0.07)
```

#### get_tools_by_tag

Recupera tools que tienen un tag específico.

```python
finance_tools = manager.get_tools_by_tag("finance")
print(f"Tools de finanzas: {finance_tools}")
```

#### remove_tool

Remueve un tool del registro.

```python
manager.remove_tool("deprecated_function")
```

#### clear_registry

Remueve todos los tools del registro.

```python
manager.clear_registry()  # Empezar de cero
```

### Cargando Tools Dinámicamente

AgentCapabilities proporciona métodos para cargar tools desde varias fuentes:

```python
# Cargar desde un archivo específico
manager.load_skills.from_file("./math_skills.py")

# Cargar desde el módulo actual
manager.load_skills.from_current()

# Cargar desde una carpeta
manager.load_skills.from_folder("./my_skills_library")

# Cargar con filtrado
manager.load_skills.from_folder(
    "./skills_library",
    by_tags=["data_processing"]
)
```

### Ejemplo Práctico: Conjuntos de Tools Especializados

```python
# Crear managers especializados para diferentes dominios
math_manager = AgentCapabilities()
math_manager.load_skills.from_file("./math_skills.py")

finance_manager = AgentCapabilities()
finance_manager.load_skills.from_file("./finance_skills.py")

data_manager = AgentCapabilities()
data_manager.load_skills.from_folder("./data_skills")

# Crear agentes con capacidades especializadas
math_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="Eres un asistente de matemáticas.",
    skills=math_manager
)

finance_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="Eres un asistente de análisis financiero.",
    skills=finance_manager
)
```

## Integración de InstantNeo y AgentCapabilities

Cada instancia de InstantNeo crea y mantiene automáticamente una instancia de AgentCapabilities interno.

### Estructura de AgentCapabilities Interno

Cuando creas un agente de InstantNeo, este:

1. Inicializa una instancia de AgentCapabilities internamente
2. Registra cualquier tool proporcionado durante la inicialización
3. Proporciona acceso a los métodos de AgentCapabilities a través de métodos proxy

Esta integración interna te permite usar métodos de AgentCapabilities directamente en la instancia de InstantNeo.

### Accediendo a Métodos de AgentCapabilities vía InstantNeo

La mayoría de los métodos de AgentCapabilities están disponibles directamente a través de la instancia de InstantNeo:

```python
# Estos hacen lo mismo:
agent.register_tool(my_function)  # Vía InstantNeo
agent.capabilities.register_tool(my_function)  # Acceso directo al manager interno

# Más ejemplos
names = agent.get_tool_names()
agent.remove_tool("obsolete_function")
agent.clear_registry()
```

### Acceso Directo a AgentCapabilities Interno

Puedes acceder a AgentCapabilities interno directamente:

```python
# Obtener el manager interno
manager = agent.capabilities

# Usar métodos del manager
metadata = manager.get_all_tools_metadata()
duplicates = manager.get_duplicate_tools()
```

### Ejemplo Práctico: Construyendo las Capacidades de un Agente

```python
from instantneo import InstantNeo
from instantneo.skills import tool

# Crear un agente
agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="Eres un asistente de análisis de datos."
)

# Definir y registrar tools
@tool(description="Calcular la media de una lista de números")
def mean(numbers: List[float]) -> float:
    return sum(numbers) / len(numbers)

@tool(description="Calcular la mediana de una lista de números")
def median(numbers: List[float]) -> float:
    sorted_nums = sorted(numbers)
    n = len(sorted_nums)
    if n % 2 == 0:
        return (sorted_nums[n//2 - 1] + sorted_nums[n//2]) / 2
    return sorted_nums[n//2]

# Registrar directamente con el agente
agent.register_tool(mean)
agent.register_tool(median)

# Cargar más tools desde archivos
agent.load_skills_from_file("./statistics_skills.py")
agent.load_skills_from_folder("./data_visualization_skills")

# Verificar los tools disponibles
print(f"Capacidades del agente: {agent.get_tool_names()}")
```

## Operaciones de AgentCapabilities

Las Operaciones de AgentCapabilities proporcionan operaciones poderosas basadas en conjuntos para combinar, comparar y manipular colecciones de tools.

### Operaciones Disponibles

La clase CapabilitiesOperations proporciona estos métodos clave:

- **union**: Combina tools de múltiples managers
- **intersection**: Mantiene solo tools que existen en todos los managers
- **difference**: Mantiene tools de un manager que no existen en otro
- **symmetric_difference**: Mantiene tools que existen en solo uno de dos managers
- **compare**: Identifica tools comunes y únicos entre managers

### Usando Operaciones con Managers Standalone

Comencemos con el caso más simple - operaciones entre instancias standalone de AgentCapabilities:

```python
from instantneo.skills import AgentCapabilities
from instantneo.skills import CapabilitiesOperations

# Crear managers especializados
web_skills = AgentCapabilities()
web_skills.load_skills.from_file("./web_skills.py")

database_skills = AgentCapabilities()
database_skills.load_skills.from_file("./database_skills.py")

# Crear un manager con tools combinados
backend_skills = CapabilitiesOperations.union(web_skills, database_skills)
print(f"Tools de backend combinados: {backend_skills.get_tool_names()}")

# Encontrar tools comunes entre managers
common_skills = CapabilitiesOperations.intersection(web_skills, database_skills)
print(f"Tools en web y database: {common_skills.get_tool_names()}")

# Encontrar tools únicos del desarrollo web
web_only = CapabilitiesOperations.difference(web_skills, database_skills)
print(f"Tools solo de web: {web_only.get_tool_names()}")

# Comparar conjuntos de tools
comparison = CapabilitiesOperations.compare(web_skills, database_skills)
print(f"Tools comunes: {comparison['common_skills']}")
print(f"Tools solo de web: {comparison['unique_to_a']}")
print(f"Tools solo de database: {comparison['unique_to_b']}")
```

### Operaciones Entre Agentes de InstantNeo

Los agentes de InstantNeo proporcionan acceso directo a estas operaciones:

```python
from instantneo import InstantNeo

# Crear agentes especializados
frontend_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="Eres un asistente de desarrollo frontend."
)
frontend_agent.load_skills_from_file("./frontend_skills.py")

backend_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="Eres un asistente de desarrollo backend."
)
backend_agent.load_skills_from_file("./backend_skills.py")

# Crear un agente full-stack
fullstack_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="Eres un asistente de desarrollo full-stack."
)

# Combinar tools de ambos agentes especializados
fullstack_agent.sm_ops_union(frontend_agent, backend_agent)
print(f"Tools full-stack: {fullstack_agent.get_tool_names()}")

# Comparar cobertura de tools
comparison = fullstack_agent.sm_ops_compare(frontend_agent)
print(f"Tools únicos de fullstack: {comparison['unique_to_a']}")
print(f"Tools en ambos: {comparison['common_skills']}")
```

### Mezclando Managers y Agentes

También puedes combinar AgentCapabilities con agentes de InstantNeo:

```python
# Crear un manager standalone de tools utilitarios
utility_manager = AgentCapabilities()
utility_manager.load_skills.from_file("./utility_skills.py")

# Agregar estos tools utilitarios a un agente existente
data_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="Eres un asistente de ciencia de datos."
)
data_agent.load_skills_from_file("./data_science_skills.py")

# Agregar tools utilitarios al agente de datos
data_agent.sm_ops_union(utility_manager)
print(f"Tools del agente de datos después de agregar utilitarios: {data_agent.get_tool_names()}")
```

### Ejemplo del Mundo Real: Construyendo un Asistente de Investigación Especializado

```python
from instantneo import InstantNeo
from instantneo.skills import AgentCapabilities, tool

# Crear managers para diferentes dominios de investigación
statistics_manager = AgentCapabilities()
statistics_manager.load_skills.from_file("./statistics_skills.py")

nlp_manager = AgentCapabilities()
nlp_manager.load_skills.from_file("./nlp_skills.py")

visualization_manager = AgentCapabilities()
visualization_manager.load_skills.from_file("./visualization_skills.py")

# Crear un agente de investigación base
research_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="""Eres un asistente de investigación especializado en análisis de datos.
    Ayudas a procesar datos, ejecutar análisis estadísticos e interpretar resultados."""
)

# Agregar dominios especializados según las necesidades de investigación
project_type = "text_analysis"  # Podría determinarse dinámicamente

if project_type == "statistical_analysis":
    research_agent.sm_ops_union(statistics_manager, visualization_manager)
elif project_type == "text_analysis":
    research_agent.sm_ops_union(nlp_manager, visualization_manager)
elif project_type == "comprehensive":
    research_agent.sm_ops_union(statistics_manager, nlp_manager, visualization_manager)

# Agregar tools personalizados específicos del proyecto
@tool(
    description="Cargar dataset desde el repositorio del proyecto",
    parameters={"dataset_name": "Nombre del dataset a cargar"}
)
def load_project_dataset(dataset_name: str) -> dict:
    # Implementación...
    return {"data": [...], "metadata": {...}}

research_agent.register_tool(load_project_dataset)

# Verificar el conjunto final de tools
print(f"Capacidades del asistente de investigación: {research_agent.get_tool_names()}")

# Usar el agente con su conjunto especializado de tools
response = research_agent.run(
    prompt="Analiza la distribución de sentimiento en nuestro dataset de feedback de clientes"
)
```

## Conclusión

El sistema de tools de InstantNeo proporciona un framework para extender las capacidades de los LLM con funciones personalizadas. La combinación del decorador `@tool` para definir capacidades y AgentCapabilities para organizarlos crea una arquitectura flexible que puede adaptarse a una amplia gama de casos de uso.

Al entender cómo crear tools bien descritos, gestionarlos eficientemente y componerlos en *AgentCapabilities* usando operaciones como union e intersection, puedes construir agentes de IA altamente capaces adaptados a tus necesidades específicas.
