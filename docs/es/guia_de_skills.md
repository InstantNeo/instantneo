# Guía de Skills de InstantNeo

## Introducción a las Skills

Las skills son los bloques de construcción fundamentales de capacidades en InstantNeo que empoderan a tus agentes LLM para realizar funciones específicas. Representan una abstracción poderosa construida sobre la capacidad de "function calling" o "tool use" de los modelos de lenguaje modernos.

### ¿Qué Son las Skills?

Las skills en InstantNeo son funciones de Python decoradas con metadata que:

1. Definen su propósito (descripción)
2. Especifican sus parámetros y tipos
3. Categorizan funcionalidad (vía tags)

Cuando un agente LLM encuentra una tarea que coincide con el propósito de una skill, puede invocar esa skill a través de sus capacidades de uso de herramientas, pasando los argumentos apropiados para realizar tareas que de otra manera podrían estar más allá de las capacidades del modelo.

### Relación con Function Calling

Las skills son la implementación de InstantNeo de la capacidad de function calling/tool use que proveedores como OpenAI, Anthropic y otros han introducido. Estas capacidades permiten a los LLMs:

1. Reconocer cuándo un tool o función específica debe usarse
2. Generar los parámetros correctos para llamar esa función
3. Integrar los resultados de vuelta en sus respuestas

El sistema de skills de InstantNeo expande este concepto con características adicionales:

- Interfaz consistente a través de diferentes proveedores de LLM
- Metadata rica para mejor descubrimiento y uso de skills por parte de los LLM
- Control de ejecución
- Herramientas de composición y organización de skills con SkillManager

InstantNeo hace que la gestión de herramientas sea simple y clara, para atender las necesidades de manejo del contexto en el desarrollo de sistemas de agentes.

### El Propósito Principal de las Skills

Las skills extienden las capacidades de tu agente más allá de la generación de texto. Por ejemplo, podrían incluir capacidades para:

- **Realizar cálculos**: Operaciones matemáticas, conversiones, estadísticas
- **Acceder sistemas externos**: Bases de datos, APIs, sistemas de archivos
- **Procesar datos**: Transformaciones, filtrado, análisis
- **Interactuar con herramientas**: Búsquedas web, generación de imágenes, notificaciones
- **Lógica de negocio personalizada**: Algoritmos y workflows específicos del dominio

## El Decorador @skill

El corazón del sistema de skills de InstantNeo es el decorador `@skill`, que transforma funciones regulares de Python en capacidades que los agentes LLM pueden descubrir y usar.

### Qué Hace el Decorador

Cuando aplicas `@skill` a una función:

1. **Captura metadata**: Almacena la descripción, info de parámetros y tags. Si la metadata no es provista, buscará el docstring de la función.
2. **Extrae información de tipo**: Usa los type hints de Python para identificar tipos de parámetros
3. **Crea tracking de ejecución**: Agrega funcionalidad para monitorear llamadas y resultados
4. **Formatea para LLMs**: Prepara la función para ser descubierta por modelos de lenguaje, según el formato para declarar herramientas.

### Sintaxis del Decorador

```python
@skill(
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    tags: Optional[List[str]] = None,
    version: Optional[str] = "1.0",
    **additional_metadata
)
```

## Creando Skills

Examinemos cómo crear skills efectivas para tus agentes de InstantNeo.

### Creación Básica de Skills

La skill más simple requiere solo una función con el decorador `@skill`:

```python
from instantneo.skills import skill

@skill(
    description="Sumar dos números y devolver el resultado"
)
def add(a: int, b: int) -> int:
    return a + b
```

### Metadata Requerida y Opcional

Técnicamente, el único parámetro requerido es la función misma. Sin embargo, para un uso efectivo de las skills:

- **description**: Altamente recomendado para ayudar al LLM a entender cuándo usar la skill, y cómo aprovechara correctamente
- **parameters**: Opcional pero recomendado para mejores descripciones de parámetros, especialmente en casos en los que se necesita guiar más al modelo o parámetros complejos.
- **tags**: Opcional pero útil para organizar y filtrar skills
- **version**: Opcional para trackear cambios (por defecto "1.0")

### La Importancia de Buenas Descripciones

Una descripción bien elaborada es crucial para el uso apropiado de la skill:

```python
@skill(
    description="Calcular la distancia entre dos coordenadas geográficas usando la fórmula de Haversine, devolviendo el resultado en kilómetros"
)
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Implementación...
```

### Descripciones de Parámetros

Aunque no son obligatorias, las descripciones de parámetros ayudan mucho al LLM a entender qué argumentos proporcionar:

```python
@skill(
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

### Type Hints: Esenciales para las Skills

Los type hints son cruciales en las skills ya que **le dicen al LLM qué tipos de datos proporcionar como argumentos**

```python
@skill(
    description="Filtrar una lista para mantener solo valores dentro de un rango especificado"
)
def filter_range(values: List[float], min_value: float, max_value: float) -> List[float]:
    return [v for v in values if min_value <= v <= max_value]
```

### Ejemplo Completo de Skill

Aquí hay una skill completa y bien diseñada:

```python
@skill(
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

### Ventajas de las Skills de InstantNeo

1. **Simplicidad**: Escribe funciones regulares de Python con metadata adicional
2. **No se requieren docstrings**: La metadata se proporciona directamente en el decorador
3. **Type safety**: Los type hints aseguran tipos de argumentos correctos
4. **Descubribilidad**: La metadata ayuda a los LLMs a encontrar y usar la skill correcta, y a usarla adecuadamente.
5. **Reutilización**: Las skills pueden compartirse entre diferentes agentes

## El SkillManager

El SkillManager es un sistema de registro que organiza y gestiona skills para uso de los agentes de InstantNeo.

### Propósito del SkillManager

El SkillManager:

1. Proporciona un registro centralizado para las skills
2. Maneja el registro y descubrimiento de skills
3. Gestiona la metadata de las skills
4. Resuelve potenciales conflictos de nombres
5. Permite organización a través de tags
6. Facilita la carga dinámica de skills

### Creando y Usando un SkillManager

```python
from instantneo.skills import SkillManager, skill

# Crear un skill manager
manager = SkillManager()

@skill(description="Calcular el cuadrado de un número")
def square(x: float) -> float:
    return x * x

# Registrar la skill
manager.register_skill(square)

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

### Métodos Clave del SkillManager

#### register_skill

Agrega una skill al registro.

```python
manager.register_skill(my_function)
```

#### get_skill_names

Devuelve una lista de todos los nombres de skills registradas.

```python
skill_names = manager.get_skill_names()
print(f"Skills disponibles: {skill_names}")
```

#### get_skill_by_name

Recupera una función skill por su nombre.

```python
calculation_skill = manager.get_skill_by_name("calculate_tax")
if calculation_skill:
    result = calculation_skill(amount=100, rate=0.07)
```

#### get_skills_by_tag

Recupera skills que tienen un tag específico.

```python
finance_skills = manager.get_skills_by_tag("finance")
print(f"Skills de finanzas: {finance_skills}")
```

#### remove_skill

Remueve una skill del registro.

```python
manager.remove_skill("deprecated_function")
```

#### clear_registry

Remueve todas las skills del registro.

```python
manager.clear_registry()  # Empezar de cero
```

### Cargando Skills Dinámicamente

SkillManager proporciona métodos para cargar skills desde varias fuentes:

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

### Ejemplo Práctico: Conjuntos de Skills Especializadas

```python
# Crear managers especializados para diferentes dominios
math_manager = SkillManager()
math_manager.load_skills.from_file("./math_skills.py")

finance_manager = SkillManager()
finance_manager.load_skills.from_file("./finance_skills.py")

data_manager = SkillManager()
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

## Integración de InstantNeo y SkillManager

Cada instancia de InstantNeo crea y mantiene automáticamente un SkillManager interno.

### Estructura del SkillManager Interno

Cuando creas un agente de InstantNeo, este:

1. Inicializa una instancia de SkillManager internamente
2. Registra cualquier skill proporcionada durante la inicialización
3. Proporciona acceso a los métodos del SkillManager a través de métodos proxy

Esta integración interna te permite usar métodos del SkillManager directamente en la instancia de InstantNeo.

### Accediendo a Métodos del SkillManager vía InstantNeo

La mayoría de los métodos del SkillManager están disponibles directamente a través de la instancia de InstantNeo:

```python
# Estos hacen lo mismo:
agent.register_skill(my_function)  # Vía InstantNeo
agent.skill_manager.register_skill(my_function)  # Acceso directo al manager interno

# Más ejemplos
names = agent.get_skill_names()
agent.remove_skill("obsolete_function")
agent.clear_registry()
```

### Acceso Directo al SkillManager Interno

Puedes acceder al SkillManager interno directamente:

```python
# Obtener el manager interno
manager = agent.skill_manager

# Usar métodos del manager
metadata = manager.get_all_skills_metadata()
duplicates = manager.get_duplicate_skills()
```

### Ejemplo Práctico: Construyendo las Capacidades de un Agente

```python
from instantneo import InstantNeo
from instantneo.skills import skill

# Crear un agente
agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="Eres un asistente de análisis de datos."
)

# Definir y registrar skills
@skill(description="Calcular la media de una lista de números")
def mean(numbers: List[float]) -> float:
    return sum(numbers) / len(numbers)

@skill(description="Calcular la mediana de una lista de números")
def median(numbers: List[float]) -> float:
    sorted_nums = sorted(numbers)
    n = len(sorted_nums)
    if n % 2 == 0:
        return (sorted_nums[n//2 - 1] + sorted_nums[n//2]) / 2
    return sorted_nums[n//2]

# Registrar directamente con el agente
agent.register_skill(mean)
agent.register_skill(median)

# Cargar más skills desde archivos
agent.load_skills_from_file("./statistics_skills.py")
agent.load_skills_from_folder("./data_visualization_skills")

# Verificar las skills disponibles
print(f"Capacidades del agente: {agent.get_skill_names()}")
```

## Operaciones del SkillManager

Las Operaciones del SkillManager proporcionan operaciones poderosas basadas en conjuntos para combinar, comparar y manipular colecciones de skills.

### Operaciones Disponibles

La clase SkillManagerOperations proporciona estos métodos clave:

- **union**: Combina skills de múltiples managers
- **intersection**: Mantiene solo skills que existen en todos los managers
- **difference**: Mantiene skills de un manager que no existen en otro
- **symmetric_difference**: Mantiene skills que existen en solo uno de dos managers
- **compare**: Identifica skills comunes y únicas entre managers

### Usando Operaciones con Managers Standalone

Comencemos con el caso más simple - operaciones entre instancias standalone de SkillManager:

```python
from instantneo.skills import SkillManager
from instantneo.skills.skill_manager_operations import SkillManagerOperations

# Crear managers especializados
web_skills = SkillManager()
web_skills.load_skills.from_file("./web_skills.py")

database_skills = SkillManager()
database_skills.load_skills.from_file("./database_skills.py")

# Crear un manager con skills combinadas
backend_skills = SkillManagerOperations.union(web_skills, database_skills)
print(f"Skills de backend combinadas: {backend_skills.get_skill_names()}")

# Encontrar skills comunes entre managers
common_skills = SkillManagerOperations.intersection(web_skills, database_skills)
print(f"Skills en web y database: {common_skills.get_skill_names()}")

# Encontrar skills únicas del desarrollo web
web_only = SkillManagerOperations.difference(web_skills, database_skills)
print(f"Skills solo de web: {web_only.get_skill_names()}")

# Comparar conjuntos de skills
comparison = SkillManagerOperations.compare(web_skills, database_skills)
print(f"Skills comunes: {comparison['common_skills']}")
print(f"Skills solo de web: {comparison['unique_to_a']}")
print(f"Skills solo de database: {comparison['unique_to_b']}")
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

# Combinar skills de ambos agentes especializados
fullstack_agent.sm_ops_union(frontend_agent, backend_agent)
print(f"Skills full-stack: {fullstack_agent.get_skill_names()}")

# Comparar cobertura de skills
comparison = fullstack_agent.sm_ops_compare(frontend_agent)
print(f"Skills únicas de fullstack: {comparison['unique_to_a']}")
print(f"Skills en ambos: {comparison['common_skills']}")
```

### Mezclando Managers y Agentes

También puedes combinar SkillManagers con agentes de InstantNeo:

```python
# Crear un manager standalone de skills utilitarias
utility_manager = SkillManager()
utility_manager.load_skills.from_file("./utility_skills.py")

# Agregar estas skills utilitarias a un agente existente
data_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="Eres un asistente de ciencia de datos."
)
data_agent.load_skills_from_file("./data_science_skills.py")

# Agregar skills utilitarias al agente de datos
data_agent.sm_ops_union(utility_manager)
print(f"Skills del agente de datos después de agregar utilitarias: {data_agent.get_skill_names()}")
```

### Ejemplo del Mundo Real: Construyendo un Asistente de Investigación Especializado

```python
from instantneo import InstantNeo
from instantneo.skills import SkillManager, skill

# Crear managers para diferentes dominios de investigación
statistics_manager = SkillManager()
statistics_manager.load_skills.from_file("./statistics_skills.py")

nlp_manager = SkillManager()
nlp_manager.load_skills.from_file("./nlp_skills.py")

visualization_manager = SkillManager()
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

# Agregar skills personalizadas específicas del proyecto
@skill(
    description="Cargar dataset desde el repositorio del proyecto",
    parameters={"dataset_name": "Nombre del dataset a cargar"}
)
def load_project_dataset(dataset_name: str) -> dict:
    # Implementación...
    return {"data": [...], "metadata": {...}}

research_agent.register_skill(load_project_dataset)

# Verificar el conjunto final de skills
print(f"Capacidades del asistente de investigación: {research_agent.get_skill_names()}")

# Usar el agente con su conjunto especializado de skills
response = research_agent.run(
    prompt="Analiza la distribución de sentimiento en nuestro dataset de feedback de clientes"
)
```

## Conclusión

El sistema de skills de InstantNeo proporciona un framework para extender las capacidades de los LLM con funciones personalizadas. La combinación del decorador `@skill` para definir capacidades y el SkillManager para organizarlas crea una arquitectura flexible que puede adaptarse a una amplia gama de casos de uso.

Al entender cómo crear skills bien descritas, gestionarlas eficientemente y componerlas en *skill managers* usando operaciones como union e intersection, puedes construir agentes de IA altamente capaces adaptados a tus necesidades específicas.