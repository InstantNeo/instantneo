# History — diseño y API

Documento de la primera capa de la arquitectura event-sourced para InstantLoop: **el History**, sus **Entries** y sus **Vistas**. No incluye Triggers, Loop ni bridge — esas piezas se documentan por separado a medida que se cierren.

---

## Idea central

El `History` es un log inmutable, append-only, donde **todo** lo que pasa en un run se guarda como `Entry`s atribuidas y temporalmente ordenadas. Es la única fuente de verdad de la arquitectura.

Las **vistas** son funciones puras registradas en una instancia de History que proyectan el log para un consumidor concreto (típicamente un agente). El History no sabe nada del agente; las vistas son la capa de presentación.

**Reglas que sostienen el diseño:**

- Nadie muta entries existentes. Las "modificaciones" son nuevas entries con `refs` apuntando a las afectadas.
- El History es **pasivo**: no emite eventos, no notifica, no tiene observers. Solo guarda y devuelve.
- Las vistas son **puras**: misma history → mismo output. Sin estado, sin side effects, sin I/O. Se ejecutan fresh cada vez.
- El History **no valida** el `type` ni el shape de `content`. Convenciones documentadas, no enforcement por código.

---

## Entry — la unidad de dato

```python
@dataclass(frozen=True)
class Entry:
    id: int                              # asignado por History al append
    author: str                          # quién la creó: "agent_a", "M", "user", "orchestrator", ...
    timestamp: float                     # asignado por History al append (time.time())
    type: str                            # qué clase de entry es. STRING ARBITRARIO
    content: dict = field(default_factory=dict)
    refs: tuple[int, ...] = ()           # ids de OTRAS entries que esta referencia/cubre/reemplaza

    def to_dict(self) -> dict: ...       # serialización JSON-safe
```

### Reglas

- Inmutable (`frozen=True`). Una entry creada nunca cambia.
- `id` y `timestamp` los asigna `History.append()`. El caller no los provee.
- `author`, `type`, `content` los provee el caller.
- `type` es un `str` arbitrario. La librería NO valida types — los users pueden inventar los suyos libremente.
- `content` es un dict abierto. Su shape depende del `type` (convención, no enforcement).
- `refs` es una tuple de ids de otras entries. Default `()`.
- `to_dict()` produce serialización JSON-safe (con manejo defensivo de tipos no estándar dentro de `content`).

### Convención canónica de `type` y `content`

No enforzada por código. Es un acuerdo entre productores y consumidores nativos.

| `type` | `content` |
|---|---|
| `prompt` | `text`, opcional `images: [{url\|path\|blob_id, detail?}]` |
| `response` | `text, step_num, finish_reason, usage, provider, model, duration_ms, reasoning, llm_calls` |
| `tool_call` | `name, arguments (dict), result (nativo), exception, execution_mode, razonamiento, step_num` |
| `summary` | `text` (+ `refs` apuntando a entries cubiertas), opcional `preserved_images` |
| `redaction` | opcional `reason` (+ `refs` apuntando a entries ocultadas) |
| `note` | `text`, opcional `addressed_to`, opcional `images` |
| `step_start` | `step_num`, opcional `step_name`, opcional `tools_available` |
| `step_end` | `step_num, duration_ms` |
| `error` | `exception, exception_type, step_num` |
| `stop_signal` | `reason` |
| `run_start` | `run_id, started_at, max_steps, view_name, agent: {name, provider, model, system_prompt, tools_available}, trigger_names, extras` |
| `run_end` | `completed_at, duration_s, terminated_reason` |

### Imágenes

Cualquier entry puede llevar `content["images"]: list[{url|path|blob_id, detail?}]`. La entry guarda **solo referencias**, nunca binarios. La conversión final (a base64 o URL pública) ocurre en el adapter del provider, no en la entry ni en la vista.

### Constantes opcionales (`instantneo/history/types.py`)

Para evitar typos en los types canónicos:

```python
RESPONSE     = "response"
TOOL_CALL    = "tool_call"
SUMMARY      = "summary"
REDACTION    = "redaction"
NOTE         = "note"
STEP_START   = "step_start"
STEP_END     = "step_end"
ERROR        = "error"
STOP_SIGNAL  = "stop_signal"
PROMPT       = "prompt"
RUN_START    = "run_start"
RUN_END      = "run_end"
```

Uso opcional: `history.append(type=types.RESPONSE, ...)`. Los types custom siguen siendo strings libres (`history.append(type="bookmark", ...)`).

---

## History — el container

Pasivo. Storage de entries + registry de vistas. Sin estado fuera de lo que appendea el caller.

```python
class History:
    def __init__(self, name: str | None = None):
        ...

    # ── Storage de entries ─────────────────────────
    def append(self, *, author: str, type: str,
               content: dict, refs: tuple[int, ...] = ()) -> Entry: ...
    def get(self, id: int) -> Entry: ...
    def all(self) -> list[Entry]: ...
    def by_author(self, author: str) -> list[Entry]: ...
    def by_type(self, type: str) -> list[Entry]: ...

    # ── Registro y ejecución de vistas ─────────────
    def view(self, name: str) -> Callable: ...        # decorator
    def add_view(self, name: str, fn: Callable) -> None: ...
    def export(self, name: str) -> Any: ...
    def list_views(self) -> list[str]: ...
    def has_view(self, name: str) -> bool: ...

    # ── Serialización ──────────────────────────────
    def to_json(self) -> str: ...
    def to_dicts(self) -> list[dict]: ...
```

### Constructor

```python
history = History()
# o con un nombre opcional para debug / multi-history
history = History(name="main")
```

Sin más parámetros. Al instanciar, dos vistas built-in quedan pre-registradas (ver más abajo).

### Storage

- `append(author, type, content, refs=())`: asigna `id` (auto-incremental, empezando en 1) y `timestamp` (`time.time()`), retorna la `Entry` creada.
- `get(id)`: levanta `KeyError` si no existe.
- `all()`: lista en orden de `id` ascendente (= orden cronológico).
- `by_author`, `by_type`: filtros simples sobre `all()`.
- Sin `update`, sin `delete`. Inmutabilidad estricta.
- Subclases para persistencia (`FileHistory`, `RedisHistory`, etc.) implementan la misma interface.

### Registry de vistas

- `view(name)`: decorator. Internamente es `add_view(name, fn)`. Devuelve la función original, así que sigue siendo invocable directamente.
- `add_view(name, fn)`: imperativo. Sobrescribe si ya existía una vista con ese nombre.
- `export(name)`: ejecuta la función registrada pasándole `self` (el history), retorna lo que la función devuelve. Levanta `KeyError` si no existe la vista.
- `list_views()`: nombres de vistas registradas.
- `has_view(name)`: bool.

### Serialización

- `to_json()`: string JSON con todas las entries.
- `to_dicts()`: lista de dicts (cada uno producido por `Entry.to_dict()`).
- Uso típico: debug, persistencia simple, transmisión externa, fixtures de tests.

---

## Vistas — funciones puras registradas

### Signatura

```python
View = Callable[[History], Any]
```

Recibe el History entero, devuelve lo que el consumidor espera — típicamente `str` markdown o `list[dict]` de messages. Tipo de retorno libre; depende del consumidor.

### Dos formas equivalentes de registrar

**(a) Decorator — para definición inline:**

```python
@history.view("for_a")
def for_a(history):
    entries = history.all()
    entries = [e for e in entries if e.author in {"A", "M"}]
    entries = apply_summaries(entries)
    return markdown_format(entries)
```

**(b) Imperativo — para funciones reusables / importadas:**

```python
def for_a(history):
    ...

history.add_view("for_a", for_a)

# misma función registrable en múltiples histories:
h1.add_view("for_a", for_a)
h2.add_view("for_a", for_a)
```

El decorator es azúcar sobre `add_view`:

```python
def view(self, name):
    def decorator(fn):
        self.add_view(name, fn)
        return fn   # devuelve la función original, sigue siendo callable
    return decorator
```

### Reglas

(No enforzadas por código, pero rotas a tu cuenta y riesgo.)

- **Puras**: misma history → mismo output. Sin estado, sin side effects, sin I/O.
- **Rápidas**: solo lectura del History y transformación. Nunca llamar a un LLM en una vista. Si hace falta trabajo caro, lo hace un Trigger que appendea entries; la vista solo proyecta lo que ya está.
- **Filtran lo operacional**: las vistas que alimentan al agente deben excluir entries de tipo `step_start`, `step_end`, `error`, `stop_signal`, `run_start`, `run_end` salvo que el caso lo justifique. El agente típicamente no debería ver el "andamiaje" del run.

### Vistas built-in pre-registradas

Al instanciar `History()`, dos vistas vienen pre-registradas:

| Vista | Qué hace | Para qué |
|---|---|---|
| `raw` | Markdown de TODAS las entries, incluido lo operacional | Debug, audit |
| `agent_default` | Filtra operacionales, aplica `apply_summaries` y `apply_redactions`, formato markdown | Default razonable para alimentar a un agente sin escribir vista custom |

Cualquier user puede sobrescribir registrando con el mismo nombre:

```python
@history.view("agent_default")
def my_default(history):
    ...   # mi versión
```

### Uso típico desde el orquestador

```python
markdown_str = history.export("for_a")
```

El orquestador (cuando lo definamos) recibe el nombre de la vista en su constructor y llama `history.export(view)` cada turno para armar el prompt del agente.

### Queries directas sin vista

Una vista produce output formateado para un consumidor. Para queries de código (debug, triggers, etc.), no hace falta una vista — la API directa del History alcanza:

```python
history.all()                                 # todas las entries
history.get(42)                               # una específica
history.by_author("M")
history.by_type("summary")
[e for e in history.all() if 17 in e.refs]    # comprehension custom
```

Si querés salir del proceso Python (jq, dashboards), `history.to_json()` o `history.to_dicts()`.

---

## Helpers opt-in (no parte del core)

Las vistas built-in y los ejemplos hacen referencia a funciones como `apply_summaries`, `apply_redactions`, `markdown_format`, `messages_format`. Estas son **convenience opinionada**, no parte del core. Viven en `instantneo/history/utils.py` (o segmentado en submódulos si crece).

Lo que ship-eamos en utils, lista cerrada inicial:

- `apply_summaries`, `apply_redactions` — lógica de refs no trivial.
- `markdown_format`, `messages_format` — formatos de salida.

Cualquier otro patrón (filtros por autor, ventanas, queries específicas) lo escribe el user inline mientras no aparezca repetido en código real. Si más adelante un patrón se vuelve común, se promueve a `utils.py`.

**Nada del core de History exige usar utils.** Un user que quiera escribir vistas y consumir el History sin importar nada de utils puede hacerlo y la librería sigue funcionando.

---

## Ejemplos de uso

### Caso mínimo: sin helpers, todo inline

```python
from instantneo.history import History

history = History()

@history.view("simple")
def simple(history):
    entries = history.all()
    return "\n".join(
        f"[{e.author}] {e.content.get('text', '')}"
        for e in entries
        if e.type in {"prompt", "response"}
    )

history.append(author="user", type="prompt", content={"text": "hola"})
history.append(author="A", type="response", content={"text": "hola, ¿en qué te ayudo?"})

print(history.export("simple"))
# [user] hola
# [A] hola, ¿en qué te ayudo?
```

### Caso con utils

```python
from instantneo.history import History
from instantneo.history.utils import apply_summaries, apply_redactions, markdown_format

history = History()

@history.view("for_a")
def for_a(history):
    entries = history.all()
    entries = [e for e in entries
               if e.type in {"response", "tool_call", "summary", "note"}]
    entries = [e for e in entries if e.author in {"A", "M"}]
    entries = apply_redactions(entries)
    entries = apply_summaries(entries)
    return markdown_format(entries)
```

### Vistas built-in directas

```python
history = History()
# ... appendear entries ...

print(history.list_views())                    # ['raw', 'agent_default']
debug_dump = history.export("raw")             # todo, para debug
agent_prompt = history.export("agent_default") # filtrado y formateado
```

---

## Verificación (cuando se implemente)

Tests por método, todos puros sobre instancias de `History`:

- `test_append_assigns_id_and_timestamp`
- `test_append_returns_created_entry`
- `test_get_raises_on_missing`
- `test_all_returns_chronological`
- `test_by_author`, `test_by_type`
- `test_view_decorator_registers_function`
- `test_add_view_imperative_equivalent`
- `test_export_runs_function_with_history`
- `test_export_raises_on_unknown_view`
- `test_list_views_includes_built_ins`
- `test_built_in_view_raw_includes_all_types`
- `test_built_in_view_agent_default_filters_operational`
- `test_to_json_roundtrip`
- `test_entries_are_immutable`

---

## Pendiente (a documentar en próximas vueltas)

- **Trigger** y su API (Conditions, Actions, evaluación).
- **Bridge** `run_info_to_entries` para conectar `InstantNeo` al History.
- **InstantLoop** refactor: cómo orquesta History + vistas + triggers.
- **Helpers** detallados: contenido y signaturas de las funciones de `utils.py`.
- **Estrategia de branching y migración** desde el `instant_loop.py` actual.
