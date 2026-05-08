# History — diseño y API

Documento de la primera capa de la arquitectura event-sourced para InstantLoop: **el History**, sus **Entries**, sus **Vistas** y la integración con **Monitor**. No incluye el Loop, el bridge ni los helpers — esas piezas se documentan por separado a medida que se cierran. La API del Monitor en sí vive en `monitor-design.md`.

---

## Idea central

El `History` es un log inmutable, append-only, donde se guardan `Entry`s atribuidas y temporalmente ordenadas. Es **agnóstico al dominio**: no sabe nada sobre agentes, loops, tools, prompts ni ningún concepto de aplicación. Solo guarda y devuelve.

Las **vistas** son funciones puras registradas en una instancia de History que proyectan el log para un consumidor concreto. La vista decide qué entries muestra y cómo. El History no impone nada sobre eso.

**Reglas que sostienen el diseño:**

- Nadie muta entries existentes. Las "modificaciones" son nuevas entries con `refs` apuntando a las afectadas.
- El History es **pasivo**: no emite eventos, no notifica, no tiene observers. Solo guarda y devuelve.
- Las vistas son **puras**: misma history → mismo output. Sin estado, sin side effects, sin I/O. Se ejecutan fresh cada vez.
- El History **no valida** ni el `type` ni el shape de `content`. Strings y dicts libres. Las convenciones sobre qué types existen viven en la documentación de los consumidores que las definen (Loop, utils, código de usuario), no acá.

---

## Entry — la unidad de dato

```python
@dataclass(frozen=True)
class Entry:
    id: int                              # asignado por History (auto-increment, desde 1)
    author: str                          # quién la creó: identificador libre
    timestamp: float                     # cuándo se appendeó (default: time.time(), overrideable)
    type: str                            # qué clase de entry es. STRING ARBITRARIO
    content: dict = field(default_factory=dict)
    refs: tuple[int, ...] = ()           # ids de OTRAS entries que esta referencia/cubre/reemplaza

    def to_dict(self) -> dict: ...       # serialización JSON-safe
```

### Reglas

- Inmutable (`frozen=True`). Una entry creada nunca cambia.
- `id` lo asigna `History.append()`, auto-incremental, empezando en 1. No overrideable.
- `timestamp` por default lo asigna `History.append()` con `time.time()`. **Overrideable** vía kwarg para casos de import histórico, replay determinista o sincronización entre histories.
- `author`, `type`, `content`, `refs` los provee el caller.
- `type` es un `str` arbitrario. La librería NO valida. Cualquier string sirve. Las convenciones de qué types existen las define cada consumidor en su documentación.
- `content` es un dict abierto. Su shape lo decide el productor. El History no impone schema.
- `refs` es una tuple de ids de otras entries. Default `()`.
- `to_dict()` produce serialización JSON-safe (con manejo defensivo de tipos no estándar dentro de `content`).

### Sobre el timestamp

`timestamp` representa **cuándo se appendeó la entry al History** — el momento de la escritura. NO representa eventos del dominio (e.g., "cuándo empezó el turno"). Si querés capturar momentos del dominio, eso es responsabilidad del productor: por ejemplo, un Loop puede appendear una entry tipo `step_start` con un campo `started_at` dentro de `content` que represente el momento real del inicio de su step.

Eso separa dos cosas claramente:

- **Momento de escritura al log** (`Entry.timestamp`): siempre presente, asignado por History.
- **Momentos del dominio** (semántica del consumidor): viven dentro de `content` con la semántica que el productor decida.

---

## History — el container

Pasivo. Storage de entries + registry de vistas + un Monitor asociado. Sin estado fuera de lo que appendea el caller.

```python
class History:
    def __init__(self,
                 name: str | None = None,
                 monitors: "Monitor | list[Monitor] | None" = None):
        ...

    # ── Storage de entries ─────────────────────────
    def append(self, *, author: str, type: str,
               content: dict, refs: tuple[int, ...] = (),
               timestamp: float | None = None) -> Entry: ...
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

    # ── Monitor (proxies sobre self.monitor) ───────
    monitor: "Monitor"                                # siempre existe
    def register_rule(self, when, do) -> None: ...    # proxy a self.monitor.register_rule
    def evaluate_monitor(self) -> None: ...           # equivale a self.monitor.evaluate(self)

    # ── Serialización ──────────────────────────────
    def to_json(self) -> str: ...
    def to_dicts(self) -> list[dict]: ...
```

### Constructor

```python
history = History()
# o con un nombre opcional para debug / multi-history
history = History(name="main")
# o pasándole monitors al construir (ver más abajo)
history = History(monitors=my_monitor)
history = History(monitors=[mon_a, mon_b])
```

**Sin vistas pre-registradas** — `list_views()` retorna lista vacía hasta que el caller registre alguna.

Sobre `monitors`: ver la sección dedicada más abajo.

### Storage

- `append(...)`: asigna `id` auto-incremental y `timestamp = time.time()` salvo override. Retorna la `Entry` creada.
- `get(id)`: levanta `KeyError` si no existe.
- `all()`: lista en orden de `id` ascendente.
- `by_author`, `by_type`: filtros simples sobre `all()`.
- Sin `update`, sin `delete`. Inmutabilidad estricta.
- Subclases para persistencia (`FileHistory`, `RedisHistory`, etc.) implementan la misma interface.

### Registry de vistas

- `view(name)`: decorator. Internamente es `add_view(name, fn)`. Devuelve la función original.
- `add_view(name, fn)`: imperativo. Sobrescribe si ya existía una vista con ese nombre.
- `export(name)`: ejecuta la función registrada pasándole `self` (el history), retorna lo que devuelve. Levanta `KeyError` si no existe.
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

Recibe el History entero, devuelve lo que el consumidor espera. Tipo de retorno libre — puede ser `str`, `list[dict]`, un objeto custom, lo que haga falta.

### Dos formas equivalentes de registrar

**(a) Decorator — para definición inline:**

```python
@history.view("my_view")
def my_view(history):
    entries = history.all()
    # filtrar, transformar, formatear como sea
    return ...
```

**(b) Imperativo — para funciones reusables / importadas:**

```python
def my_view(history):
    ...

history.add_view("my_view", my_view)

# misma función registrable en múltiples histories
h1.add_view("my_view", my_view)
h2.add_view("my_view", my_view)
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
- **Rápidas**: solo lectura del History y transformación. Si una vista necesita trabajo caro (e.g., correr un LLM), ese trabajo debe haber pasado antes (alguien lo appendeó como entry); la vista solo proyecta lo que ya está.

### Vistas built-in

**Ninguna.** El History no ship-ea vistas pre-registradas. Cada caller registra las que necesite.

Cuando se documenten consumidores concretos (Loop, etc.), ese consumidor podrá pre-registrar las vistas que tenga sentido para su caso de uso (por ejemplo, una vista `loop_default` específica del Loop que se registra al instanciar el Loop).

### Uso típico desde un consumidor

```python
output = history.export("my_view")
```

### Queries directas sin vista

Para queries de código (debug, custom logic, lecturas internas), no hace falta una vista — la API directa del History alcanza:

```python
history.all()
history.get(42)
history.by_author("M")
history.by_type("summary")
[e for e in history.all() if 17 in e.refs]
```

Si querés salir del proceso Python (jq, dashboards, etc.), `history.to_json()` o `history.to_dicts()`.

---

## Monitor — observación reactiva

Cada History viene con un **Monitor** asociado en el atributo `history.monitor`. El Monitor tiene reglas `(when, do)` que el orquestador (típicamente un Loop) evalúa entre steps; las reglas que matchean disparan acciones que normalmente appendean nuevas entries.

La API del Monitor en sí está documentada en `monitor-design.md`. Acá se documenta solo la integración con History.

### Cómo se inserta un Monitor

Al construir el History, vía el parámetro `monitors`. Tres casos, mismo pattern que `InstantNeo(tools=...)`:

```python
# Caso 1: una instance de Monitor → asignación directa
history = History(monitors=my_monitor)
# history.monitor IS my_monitor (mismo objeto, mutaciones se propagan)

# Caso 2: lista de monitors → se unen vía MonitorOperations.union
history = History(monitors=[monitor_a, monitor_b])
# history.monitor es un Monitor nuevo (snapshot estático de las reglas)

# Caso 3: nada → Monitor() vacío por default
history = History()
# history.monitor existe igualmente, pero sin reglas
```

`history.monitor` **siempre existe**, garantizado.

### Proxies en History

Para ergonomía del caso simple, History expone dos métodos que delegan al Monitor:

```python
history.register_rule(when, do)
# equivale a:
history.monitor.register_rule(when, do)

history.evaluate_monitor()
# equivale a:
history.monitor.evaluate(history)
```

Es legal usar cualquiera de las dos formas; son la misma operación.

### Compartir Monitors entre Histories

Como una `Monitor` instance puede attacharse a múltiples Histories vía el caso 1, podés definir un Monitor una vez y reusarlo:

```python
shared = Monitor()
shared.register_rule(when_type_present("error"), stop_with("err"))

h1 = History(monitors=shared)
h2 = History(monitors=shared)
# Ambas comparten el mismo Monitor. Mutarlo afecta a las dos.
```

### Cuándo se invoca evaluate_monitor()

Un Loop (cuando se documente) llamará `history.evaluate_monitor()` al final de cada step, después de que el agente y el bridge appendeen sus entries. Pero el `evaluate_monitor()` es público y agnóstico — cualquier orquestador o test puede invocarlo cuando necesite.

---

## Ejemplos

### Caso mínimo — registro y consulta

```python
from instantneo.history import History

history = History()

history.append(author="user", type="message", content={"text": "hola"})
history.append(author="A", type="response", content={"text": "hola, ¿en qué te ayudo?"})

print(history.all())
# [Entry(id=1, author="user", ...), Entry(id=2, author="A", ...)]

print(history.to_json())
# JSON dump completo
```

### Vista custom

```python
@history.view("simple")
def simple(history):
    entries = history.all()
    return "\n".join(
        f"[{e.author}] {e.content.get('text', '')}"
        for e in entries
    )

print(history.export("simple"))
# [user] hola
# [A] hola, ¿en qué te ayudo?
```

### Override de timestamp (import histórico, replay, sincronización)

```python
import time

# Importar una entry "histórica" con timestamp real
history.append(
    author="legacy_system", type="event",
    content={"data": ...},
    timestamp=time.time() - 3600,   # hace una hora
)
```

### Refs y queries por relación

```python
history.append(author="user", type="message", content={"text": "primero"})
history.append(author="user", type="message", content={"text": "segundo"})
history.append(
    author="M", type="reaction",
    content={"sentiment": "positive"},
    refs=(1, 2),     # esta entry se refiere a las dos primeras
)

# Encontrar entries que referencian la id 1
[e for e in history.all() if 1 in e.refs]
```

---

## Verificación (cuando se implemente)

Tests por método, todos puros sobre instancias de `History`:

- `test_append_assigns_id_and_timestamp`
- `test_append_returns_created_entry`
- `test_append_accepts_timestamp_override`
- `test_get_raises_on_missing`
- `test_all_returns_chronological_by_id`
- `test_by_author`, `test_by_type`
- `test_view_decorator_registers_function`
- `test_add_view_imperative_equivalent`
- `test_add_view_overrides_existing`
- `test_export_runs_function_with_history`
- `test_export_raises_on_unknown_view`
- `test_list_views_empty_initially`
- `test_to_json_roundtrip`
- `test_to_dicts_roundtrip`
- `test_entries_are_immutable`

---

## Pendiente (a documentar en próximas vueltas)

- **Bridge** `run_info_to_entries`: cuáles son los types que produce desde `RunInfo` (probablemente `response`, `tool_call`, posiblemente `error`). Pertenece a la sección del Loop.
- **Trigger** y su API: Conditions, Actions, evaluación entre steps.
- **InstantLoop** refactor: cómo orquesta History + vistas + triggers, qué types operacionales emite (probablemente `step_start`, `step_end`, etc.), si pre-registra una vista `loop_default`.
- **Helpers** (`apply_summaries`, `apply_redactions`, formats, etc.): biblioteca opt-in. Allí se documentan los types convencionales que esos helpers consumen.
- **Estrategia de migración** desde el `instant_loop.py` actual.
