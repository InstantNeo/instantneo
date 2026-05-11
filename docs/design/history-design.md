# History — diseño y API

Documento de la primera capa de la arquitectura event-sourced para InstantLoop: **el History**, sus **Entries** y sus **Vistas**. No incluye el Loop, el Monitor, el bridge ni los helpers — esas piezas se documentan por separado. El Monitor (rule engine que opera contra un History) vive en `monitor-design.md`; el Loop lo invoca cuando corresponde.

**Scope del History**: es el **log operacional** — captura lo que el agente necesita para continuar (responses, tool calls, errors), lo que la vista renderea, y baseline de observabilidad casual (usage, timing, model). **No es** el log de debug completo: ese vive aparte en `RunLog` (ver `log-design.md`), opt-in vía `debug=True` en el Loop. La data pesada (prompt rendered, messages_sent literal, detalle multi-call) nunca llega al History.

---

## Idea central

El `History` es un log inmutable, append-only, donde se guardan `Entry`s atribuidas y temporalmente ordenadas. Es **agnóstico al dominio**: no sabe nada sobre agentes, loops, tools, prompts ni ningún concepto de aplicación. Solo guarda y devuelve.

Las **vistas** son funciones puras registradas en una instancia de History que proyectan el log para un consumidor concreto. La vista decide qué entries muestra y cómo. El History no impone nada sobre eso.

**Reglas que sostienen el diseño:**

- Nadie muta entries existentes. Las "modificaciones" son nuevas entries con `refs` apuntando a las afectadas.
- El History es **estrictamente pasivo**: no emite eventos, no notifica, no tiene observers, no tiene Monitor adentro. Solo guarda y devuelve.
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

Pasivo. Storage de entries + registry de vistas. Sin estado fuera de lo que appendea el caller.

```python
class History:
    def __init__(self, name: str | None = None):
        ...

    # ── Storage de entries ─────────────────────────
    def append(self, *, author: str, type: str,
               content: dict, refs: tuple[int, ...] = (),
               timestamp: float | None = None) -> Entry: ...
    def append_from_run(self, run_info, *,
                        turn_num: int, author: str,
                        origin: str, run_id: str) -> list[Entry]: ...
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

    # ── Reset (deliberado) ─────────────────────────
    def reset(self) -> None: ...
```

### Constructor

```python
history = History()
# o con un nombre opcional para debug / multi-history
history = History(name="main")
```

**Sin vistas pre-registradas** — `list_views()` retorna lista vacía hasta que el caller registre alguna.

**Sin Monitor adentro** — el Monitor es una pieza separada que opera contra cualquier History. Se pasa al consumidor (típicamente un Loop) o se invoca manualmente con `monitor(history)`. Ver `monitor-design.md`.

### Storage

- `append(...)`: asigna `id` auto-incremental y `timestamp = time.time()` salvo override. Retorna la `Entry` creada.
- `append_from_run(...)`: conveniencia. Descompone un `RunInfo` (de InstantNeo) en entries y las appendea de una. Wrapper sobre la función `append_entry_from_run` documentada en `runinfo-to-entries.md`. Se invoca `history.append_from_run(run_info, turn_num=..., author=..., origin=..., run_id=...)`.
- `get(id)`: levanta `KeyError` si no existe.
- `all()`: lista en orden de `id` ascendente.
- `by_author`, `by_type`: filtros simples sobre `all()`.
- Sin `update`, sin `delete` por entry. Inmutabilidad estricta de cualquier entry individual.
- `reset()`: única operación destructiva (ver sección dedicada más abajo). Borra TODO. No es delete granular.
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
history.by_type("note")
[e for e in history.all() if 17 in e.refs]
```

Si querés salir del proceso Python (jq, dashboards, etc.), `history.to_json()` o `history.to_dicts()`.

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

## Tamaño y persistencia

### Cuánto pesa un History en RAM

Cada Entry es liviana; el peso real lo dan los `content`:

| Tipo de entry típica | Tamaño aprox |
|---|---|
| `step_start`, `step_end`, `run_end` (solo metadata) | 200-500 bytes |
| `tool_call` con args y result chicos | 1-5 KB |
| `tool_call` con result grande (e.g., scrape) | 10-100 KB |
| `response` con reasoning largo (extended thinking) | 5-50 KB |
| `prompt` con imágenes (refs livianos) | 1-10 KB |
(notar: la data pesada de debug, como `messages_sent` literal, **no** llega al History; vive aparte en el `RunLog` si se construyó con `debug=True`)

Reglas de pulgar:

| Escenario | Entries | RAM |
|---|---|---|
| Run típico (5-10 turnos) | ~30-100 | ~30-500 KB |
| Sesión multi-run (50 runs) | ~1500 | ~50-500 MB |
| Watcher de fondo corriendo días | 100k+ | GB-scale |

Hasta unos miles de entries, el History es trivial. Pasada esa marca, conviene pensar en compactación o en snapshot+reset.

### Las vistas pueden filtrar, pero la RAM no baja

Una vista puede mostrar al consumidor solo un subset de las entries (filtrar por type, por author, por run_id, lo que sea). Pero **las entries no se borran del History** — siguen en RAM, append-only, para auditoría y replay.

Es decir: la "compresión" del contexto que recibe el agente es **lógica** (decisión de la vista), no **física** (memoria). Si querés bajar la memoria también, persistís y reseteás (siguiente sección).

### `reset()` — operación deliberada y única

`history.reset()` es la única operación destructiva. Borra TODO el log y reinicia el contador de id:

```python
class History:
    def reset(self) -> None:
        """Borra todas las entries y reinicia el contador de id.

        Operación irreversible. Las refs de cualquier entry futura no podrán
        apuntar a las antiguas. Patrón seguro: persistir ANTES.
        """
```

**Patrón canónico de uso (snapshot + reset):**

```python
import json
from pathlib import Path

# 1. Persistir lo que hay
Path("session_001.json").write_text(history.to_json())

# 2. Reset: el History pasa a estar vacío
history.reset()

# 3. (Opcional) Marca de continuidad simbólica
history.append(
    author="orchestrator",
    type="session_continued",
    content={"prior_session_path": "session_001.json"},
)

# 4. Seguir trabajando
loop = InstantLoop(agent=A, history=history, ...)
loop.run("...")
```

**Reglas de doctrina:**

1. **`reset()` es nombre con peso semántico** — sugiere "vuelvo a estado inicial deliberadamente". No usamos `clear()` (suena rutinario por su uso en `dict`/`list`).
2. **No hay `delete(id)` ni `truncate(...)`** — eliminarían entries puntuales rompiendo cualquier `refs` que apunte a ellas. Si querés perder data, perdés todo de una vez con `reset()` y queda evidente.
3. **El patrón documentado siempre persiste antes** — quien escriba `reset()` sin snapshot lo hace porque así lo decidió.
4. **La doctrina canónica es append-only** — `reset()` es la excepción consciente para casos de "empezar de cero", no para gestión de memoria fina (eso va vía compactación + futuras subclases con backend).

### Persistencia incremental (patrón sin reset)

Lo más común no es resetear, sino persistir incrementalmente para tener un punto de recuperación si el proceso muere. Se hace con una rule del Monitor:

```python
def persist_to_disk(path: Path):
    def action(history):
        path.write_text(history.to_json())
    return action

monitor.add_rule(every_n_appends(50), persist_to_disk(Path("session.json")))
```

Para recuperar:

```python
history = History.from_dicts(json.load(open("session.json")))
```

(`from_dicts` es el complementario de `to_dicts()`, trivial de implementar.)

### Cuándo "termina" un History

Nunca por sí solo. El History es un objeto Python; existe hasta que el GC se lo lleve. **No tiene noción de "complete" o "closed"**.

Lo que sí tiene son momentos donde está **estable** — ningún orquestador está escribiendo:

| Caso | Momento estable |
|---|---|
| Un solo `loop.run()` | Cuando retorna |
| Varios `.run()` secuenciales | Después de cada uno |
| Watcher en background activo | Solo cuando el watcher se detuvo |
| Mixto | Cuando todos los threads finalizaron |

El History **no avisa**. Vos sabés cuándo está estable y persistís. Si querés una marca explícita en el log:

```python
history.append(
    author="orchestrator",
    type="session_end",
    content={"reason": "user_done", "completed_at": "..."},
)
```

Esa es **convención del usuario**, no del framework.

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
- `test_append_from_run_delegates_to_function` — el método de conveniencia produce el mismo resultado que `append_entry_from_run(history, ...)`.
- `test_reset_empties_entries_and_resets_id` — después de `reset()`, `all()` está vacío y la próxima entry tiene id=1.
- `test_reset_does_not_clear_views` — las vistas registradas sobreviven al reset (son metadata, no contenido).

---

## Pendiente (a documentar en próximas vueltas)

- **Helpers de formato y queries**: biblioteca opt-in que documente patrones útiles para vistas (markdown render, agrupación por turno, etc.).
- **Estrategia de migración** desde el `instant_loop.py` actual.
- **Concurrencia**: hoy `History.append` no tiene locking. Si se escribe desde múltiples threads (por ejemplo, una action en background), agregar un `threading.Lock` en `append`. Queda como ítem futuro.
