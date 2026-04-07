# InstantLoop — Orquestador multi-turno para InstantNeo

`InstantLoop` corre un agente `InstantNeo` en un loop multi-turno con historial acumulado.
No sabe de dominio: recibe configuración y produce resultado + traza.

## Concepto

- **InstantNeo** = el agente. Tiene un LLM, un system prompt y tools. Es stateless por turno.
- **InstantLoop** = el orquestador. Corre el agente en loop, acumula historial entre turnos, y detecta cuándo parar (cuando el agente llama a una tool de finalización).

La separación es intencional: InstantNeo no sabe que está en un loop, InstantLoop no sabe de dominio.

## Ejemplo

Un agente investigador que busca información y reporta cuando termina.

### 1. Definir tools y capabilities

Las tools se definen con el decorador `@tool`. Las instrucciones de cómo usar las tools van en `global_instructions` del `AgentCapabilities`, **no** en el `role_setup` del agente. Esto permite que las capabilities funcionen como plugins modulares.

```python
from instantneo import tool, AgentCapabilities

# El decorador @tool acepta:
#   description: descripción de la tool (se envía al LLM)
#   parameters: dict con metadata por parámetro (description, type, enum, etc.)
#   tags: lista de tags para filtrar tools
#   version: versión de la tool
# Si no se pasa parameters, se infieren de type hints y docstring.

@tool(
    description="Busca información sobre un tema en la base de conocimiento",
    parameters={
        "query": {"description": "Tema o pregunta a buscar", "type": "string"},
    },
)
def buscar_info(query: str) -> str:
    # Lógica de búsqueda real
    return "Resultado de la búsqueda..."


@tool(
    description="Reporta el resultado final de la investigación. Llamar solo cuando se tiene suficiente información.",
    parameters={
        "resumen": {"description": "Resumen breve de lo investigado"},
        "temas_investigados": {"description": "Lista de temas consultados"},
        "conclusiones": {"description": "Conclusiones finales del investigador"},
    },
    tags=["stop_tool"],
)
def reportar_resultado(resumen: str, temas_investigados: str, conclusiones: str) -> str:
    return "Reporte registrado."


# Las global_instructions le dicen al agente CÓMO usar las tools.
# Se inyectan automáticamente en el system prompt junto con los schemas.
caps = AgentCapabilities(
    name="investigacion",
    global_instructions="""
## Instrucciones de uso de herramientas

1. **buscar_info**: Busca un tema a la vez. Si necesitas info de varios temas,
   haz búsquedas separadas en distintos turnos.
2. **reportar_resultado**: Llama a esta herramienta SOLO cuando tengas suficiente
   información para dar una respuesta completa.

No inventes información. Solo reporta lo que encontraste con las herramientas.
""",
)
caps.register_tool(buscar_info)
caps.register_tool(reportar_resultado)
```

### 2. Crear el agente InstantNeo

El `role_setup` define la identidad del agente. Las instrucciones de herramientas ya están en las capabilities.

```python
from instantneo import InstantNeo

agent = InstantNeo(
    provider="gemini",
    api_key="...",
    model="gemini-2.5-flash",
    role_setup="Eres un investigador metódico. Tu trabajo es investigar temas usando las herramientas disponibles.",
    tools=caps,
    temperature=0.0,
    max_tokens=4096,
)
```

### 3. Crear el loop y ejecutar

```python
from instantneo.experimental.instant_loop import InstantLoop

loop = InstantLoop(
    agent=agent,
    prompt_template="Investiga sobre: {producto}\n\n{historial}",
    stop_tool="reportar_resultado",
    max_turns=10,
)

resultado = loop.run(product="lenguaje Python")
```

## Cómo funciona el loop

1. Construye el prompt reemplazando los placeholders del template (ej: `{producto}`) e inyectando `{historial}`.
2. Llama a `agent.run(prompt, images=..., image_detail=...)`.
3. Extrae las tools que el agente usó y lo que respondió.
4. Acumula todo en el historial.
5. Si el agente llamó a `stop_tool` → termina y devuelve los argumentos como resultado.
6. Si no → vuelve al paso 1 con el historial actualizado.
7. Si se agotan los turnos (`max_turns`) → termina con error.

## Parámetros de InstantLoop

### Constructor

| Parámetro | Tipo | Default | Descripción |
| --- | --- | --- | --- |
| `agent` | `InstantNeo` | *requerido* | Instancia configurada con tools y system prompt. |
| `prompt_template` | `str` | *requerido* | Template del prompt con placeholders. Debe contener `{historial}` (reservado, se inyecta automáticamente con el historial acumulado entre turnos). Puede contener otros placeholders personalizados (ej: `{producto}`) que se reemplazan con el valor pasado a `run()`. |
| `stop_tool` | `str` | `"report_classification"` | Nombre de la tool que señala fin del loop. Cuando el agente la llama, el loop termina y los argumentos de esa tool se devuelven como resultado. |
| `max_turns` | `int` | `30` | Máximo de turnos antes de forzar parada. Si se alcanza, el resultado contiene un error indicando que el agente no llamó a la stop_tool. |
| `debug_dir` | `str \| Path \| None` | `None` | Directorio base para archivos de debug. Por cada ejecución se crea una subcarpeta con timestamp y nombre de config. |
| `debug_run_dir` | `str \| Path \| None` | `None` | Carpeta de debug pre-creada. Tiene prioridad sobre `debug_dir`. Útil para evaluaciones donde el caller controla la estructura de carpetas. |
| `agent_config` | `dict \| None` | `None` | Dict con la configuración del agente. Se incluye en los archivos de debug para trazabilidad completa. No afecta la ejecución. |
| `images` | `str \| list[str] \| None` | `None` | Imágenes para incluir en cada turno. Rutas a archivos o URLs, igual que en InstantNeo. |
| `image_detail` | `str \| None` | `None` | Nivel de detalle de las imágenes: `"auto"`, `"low"`, `"high"`. |

### run()

```python
resultado = loop.run(product="texto del input")
```

El método `run()` recibe `product` (str) — el input principal que se inyecta en el placeholder `{producto}` del template.

Retorna un dict con dos claves:

- **`result`**: los argumentos que el agente pasó a la `stop_tool`, como dict. Si el agente no llamó a la stop_tool, contiene `{"error": "No llamó {stop_tool}"}`.
- **`trace`**: traza completa de la ejecución con: turnos detallados, timing, uso de tokens, historial, conteo de tools usadas.

## Imágenes

InstantLoop acepta imágenes igual que InstantNeo. Se envían en cada turno del loop:

```python
loop = InstantLoop(
    agent=agent,
    prompt_template="Analiza esta imagen: {producto}\n\n{historial}",
    stop_tool="reportar_analisis",
    max_turns=5,
    images=["ruta/a/imagen.jpg"],
    image_detail="high",
)
```

> **Nota sobre reasoning**: Actualmente `reasoning` es un parámetro de `agent.run()`, no del constructor de InstantNeo. Debería poder prefijarse en el agente base para que InstantLoop y otros orquestadores lo hereden naturalmente. Ver [issue #23](https://github.com/InstantNeo/instantneo/issues/23).

## Debug

Si se pasa `debug_dir` o `debug_run_dir`, InstantLoop genera por cada ejecución:

| Archivo | Descripción |
| --- | --- |
| `progress.json` | Estado en tiempo real del run. Se actualiza antes y después de cada turno. Útil para monitoreo en vivo. |
| `trace.json` | Dump completo: config + traza + resultado. Para consumo programático. |
| `report.md` | Markdown técnico con config, métricas y turnos detallados con prompts enviados. |
| `report.json` | JSON estructurado sin historial redundante. Pensado para dashboards. |
| `agent_trace.md` | Narrativa limpia del proceso del agente: qué herramientas usó, qué respondió, qué decidió. Para lectura humana. |

## Estructura del trace

El `trace` retornado por `loop.run()` tiene esta estructura:

```python
{
    "started_at": "2025-01-15T10:30:00+00:00",
    "completed_at": "2025-01-15T10:30:12+00:00",
    "total_duration_s": 12.5,
    "total_turns": 4,
    "total_tool_executions": 5,
    "total_usage": {
        "input_tokens": 2500,
        "output_tokens": 800,
        "total_tokens": 3300,
    },
    "tool_usage_counts": {
        "buscar_info": 3,
        "reportar_resultado": 1,
    },
    "history": [...],   # historial acumulado entre turnos
    "turns": [...],     # detalle de cada turno (provider, model, duration, tool_executions, etc.)
}
```

## Notas

- El `prompt_template` **debe** contener `{historial}`. Es el placeholder reservado donde el loop inyecta el historial acumulado entre turnos. Sin historial, el agente no tiene contexto de lo que ya hizo.
- Los otros placeholders del template (ej: `{producto}`) se reemplazan con el valor de `product` pasado a `run()`.
- InstantLoop es agnóstico al dominio. La lógica de negocio va en el system prompt, las `global_instructions` de las capabilities, y las tools.
- Las `global_instructions` del `AgentCapabilities` son el lugar correcto para las instrucciones de uso de herramientas. El `role_setup` del agente define la identidad/rol, no las instrucciones operativas.
