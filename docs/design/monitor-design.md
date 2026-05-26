# Monitor — diseño y API

Documento del **Monitor**: rule engine standalone que opera contra un `History`. Es genérico — sirve para terminación de loops, alerting, persistencia, observabilidad, auditoría, coordinación multiagente. Su uso más común es como pieza interna de un `InstantLoop`, pero el Monitor en sí no sabe nada del Loop.

**El Monitor no es parte del sistema de Debug Log** (`RunLog`, ver `log-design.md`). Son piezas ortogonales: el Monitor reacciona a entries del History con rules; el RunLog captura todo lo que pasó en formato forense. Una rule de Monitor PUEDE escribir al History (in-band) o hacer side effects (out-of-band, ej. persistir a archivo) — pero el RunLog se ocupa de una capa distinta de captura, no como reacción a rules sino como registro paralelo del Loop.

---

## Idea central

Un `Monitor` es un objeto que tiene **reglas**: pares `(when, do)` donde:

- `when` es una **condición** — función pura `Callable[[History], bool]`.
- `do` es una **acción** — función `Callable[[History], None]`, puede tener cualquier efecto.

El Monitor NO se evalúa solo. Alguien lo invoca con `monitor(history)` cuando le toca. En esa invocación, itera sus reglas en orden y dispara las que matchean.

**Reglas que sostienen el diseño:**

- **Standalone**: el Monitor no guarda referencia a ningún History. El history llega como argumento cada vez que se invoca.
- **Pasivo**: no tiene reloj interno, no tiene thread propio, no observa nada autónomamente. Solo hace algo cuando alguien lo llama.
- **Reusable**: la misma instancia puede invocarse contra múltiples Histories distintos.
- **Síncrono por default**: las acciones bloquean la invocación hasta completarse. Si una action quiere correr en background, tiene que armar su propio thread.
- **Genérico**: el Monitor no sabe del Loop ni de InstantNeo. Su única dependencia es la interface `History`.

---

## API de `Monitor`

```python
class Monitor:
    def __init__(self, name: str | None = None):
        self.name = name
        self._rules: list[tuple[Condition, Action]] = []

    def add_rule(self, when: Condition, do: Action) -> None:
        """Añade una regla (when, do) al final de la lista."""

    def __call__(self, history: "History") -> None:
        """Itera reglas y dispara las que matchean contra el history pasado."""
```

Tres métodos públicos (contando `__init__`). `name` es opcional (debug, identificación).

**Uso canónico**:

```python
monitor = Monitor()
monitor.add_rule(when_type_present("error"), stop_signal("err"))
monitor.add_rule(every_n_steps(10),          append_note("checkpoint"))

monitor(history)        # una pasada — evalúa todas las rules contra el history actual
```

Llamar al monitor como función es lo idiomático. Coherente con el resto del modelo (conditions, actions, views también son callables que reciben `history`).

---

## `MonitorOperations.union`

Para combinar varios monitors en uno:

```python
class MonitorOperations:
    @staticmethod
    def union(*monitors: Monitor, name: str | None = None) -> Monitor:
        """Combina N monitors en uno nuevo, preservando orden de reglas."""
```

Lo usan los consumidores que aceptan `monitors=` en su constructor (ej. `InstantLoop`) para fusionar listas en un único Monitor. También importable para usos manuales.

---

## Conditions y Actions

### Signatura

```python
Condition = Callable[[History], bool]
Action    = Callable[[History], None]
```

Ambas reciben el `History` completo. Adentro pueden:

- Consultar entries: `history.all()`, `history.by_type(...)`, `history.by_author(...)`, `history.get(id)`.
- Ejecutar vistas registradas: `history.export("...")`.
- Appendear nuevas entries: `history.append(...)` (in-band).
- Hacer cualquier otro efecto Python: HTTP, archivos, alertas, métricas, lo que sea (out-of-band).
- Serializar: `history.to_json()`, `history.to_dicts()`.

### Pureza

- **Conditions** deben ser puras. Misma history → mismo bool. Sin side effects, sin I/O.
- **Actions** son intencionalmente impuras. Pueden tener **cualquier efecto** que un Python normal pueda tener.

### Dos clases de efecto que puede tener una action

**In-band — el orquestador (típicamente un Loop) lo ve.**

Son las que appendean entries al History. Quienes consuman el History después (Loop, vistas, otras rules en la misma pasada) reaccionan al cambio.

| Action | Qué appendea | Quién la consume |
|---|---|---|
| `stop_signal("foo")` | `stop_signal` | un Loop la lee y rompe |
| `append_note(text)` | `note` | la vista la incluye si quiere |
| custom (cualquiera) | el type que el autor decida | quien interprete ese type |

**Out-of-band — el orquestador no se entera.**

Son las que producen cambios externos al proceso. No tocan el History.

```python
def notify_slack_on_error(webhook_url):
    def action(history):
        last_err = history.by_type("error")[-1]
        requests.post(webhook_url, json={"text": f"Error: {last_err.content['exception']}"})
    return action

def persist_history_every_step(path):
    def action(history):
        path.write_text(history.to_json())
    return action
```

El orquestador sigue como si nada hubiera pasado.

**Mezcla — efecto externo + audit trail.**

```python
def notify_and_record(webhook_url):
    def action(history):
        last_err = history.by_type("error")[-1]
        resp = requests.post(webhook_url, json={"text": f"...{last_err.content}..."})
        history.append(
            author="orchestrator",
            type="notification_sent",
            content={"channel": "slack", "status_code": resp.status_code},
        )
    return action
```

Útil cuando querés trazabilidad: "¿en qué step se notificó? ¿salió bien?"

### Sincronía

`monitor(history)` corre las reglas **secuencialmente** en el orden registrado. Cada action **bloquea** hasta terminar. Las acciones posteriores ven el estado dejado por las anteriores en la misma pasada.

Si necesitás no bloquear, tu action puede disparar un thread/task y retornar — pero las entries que produzca llegarán fuera de orden respecto al step. Nota: si vas a appendear desde un thread paralelo, el `History` necesita locking en `append` (hoy no lo tiene; ver `history-design.md`).

---

## Conditions built-in

Funciones puras importables. Set chico, foco en lo predictivamente útil.

### Sobre cantidad y tipo

| Función | Qué hace |
|---|---|
| `when_entry_count_above(n)` | Total de entries > n |
| `when_type_count_above(type, n)` | Entries del `type` > n |
| `when_author_count_above(author, n)` | Entries del `author` > n |
| `when_type_present(type)` | Al menos una entry de ese `type` existe |

### Sobre la última entry

| Función | Qué hace |
|---|---|
| `when_last_is_type(type)` | La última entry tiene ese `type` |
| `when_last_is_author(author)` | La última entry es de ese `author` |
| `when_last_content_matches(predicate)` | El `content` de la última entry pasa el predicado |

### Sobre tokens (asume una vista registrada)

| Función | Qué hace |
|---|---|
| `when_tokens_above(view_name, n, tokenizer=None)` | El output de `history.export(view_name)` supera `n` tokens |

`tokenizer` es opcional. Default: estimación basada en chars (`len(text) // 4`). Pasale uno preciso si te importa la exactitud:

```python
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
when_tokens_above("agent_default", 100_000, tokenizer=lambda s: len(enc.encode(s)))
```

### Sobre steps (asume convención del Loop)

Estas asumen que el Loop appendea entries `type="step_start"` con `content["step_num"]`. Si no usás un Loop con esa convención, no funcionan.

| Función | Qué hace |
|---|---|
| `every_n_steps(n)` | True cuando el último `step_num` es múltiplo de `n` |
| `at_step(k)` | True cuando el último `step_num` es exactamente `k` |

### Combinadores

| Función | Qué hace |
|---|---|
| `And(*conds)` | Todas las conditions deben cumplirse |
| `Or(*conds)` | Al menos una se cumple |
| `Not(cond)` | La negación |

---

## Actions built-in (in-band)

Set mínimo, dos:

| Función | Qué hace |
|---|---|
| `stop_signal(text)` | Appendea `Entry(type="stop_signal", content={"text": text, "origin": current_origin(history), "run_id": current_run_id(history)})`. Un Loop la lee — si el `text` está en la whitelist `stop_signals` del Loop, rompe |
| `append_note(text, author="orchestrator")` | Appendea `Entry(type="note", content={"text": text})` |

### Implementación canónica de `stop_signal`

```python
from instantneo.history.queries import current_run_id, current_origin

def stop_signal(text: str):
    """Action factory: appendea un stop_signal con el texto dado.

    El Loop, si lo escucha (vía su parámetro `stop_signals=[..., text, ...]`),
    rompe el run con stop_reason=text.
    """
    def action(history):
        history.append(
            author="orchestrator",
            type="stop_signal",
            content={
                "text":   text,
                "origin": current_origin(history),
                "run_id": current_run_id(history),
            },
        )
    return action
```

El Loop **solo lee `content["text"]`** y compara con su whitelist. Los otros campos (`origin`, `run_id`) son para auditoría posterior, no para el matching.

Cualquier otra action — invocar a otro agente para que produzca algún tipo de entry, persistir a disco, notificar Slack, etc. — es **función custom del usuario**. La librería no asume convenciones más allá de `stop_signal` (contrato del Loop) y `note` (utilidad genérica).

Las **out-of-band** (notificaciones, persistencia, métricas, HTTP) son siempre custom — no hay built-ins porque dependen del stack del usuario. Ejemplos viven en docs/recipes, no en el core.

---

## Custom

Conditions y actions custom son funciones planas de Python. Sin subclassing, sin decoradores, sin registrar en ningún lado.

### Condition simple

```python
def when_user_present(history):
    return any(e.author == "user" for e in history.all())
```

### Condition con parámetros (factory)

```python
def when_more_than(n: int):
    def cond(history):
        return len(history.all()) > n
    return cond

monitor.add_rule(when_more_than(50), my_action)
```

### Condition multipropósito (regex sobre content serializado)

Si solo usás el shape de Entry y/o serializás el `content`, una condition funciona contra cualquier History sin importar de qué orquestador venga:

```python
import re, json

def when_any_content_matches(pattern: str, in_types=None):
    """True si el regex matchea en el content de alguna entry."""
    rx = re.compile(pattern)
    def cond(history):
        entries = history.all()
        if in_types:
            entries = [e for e in entries if e.type in in_types]
        for e in entries:
            blob = json.dumps(e.content, default=str, ensure_ascii=False)
            if rx.search(blob):
                return True
        return False
    return cond

monitor.add_rule(
    when_any_content_matches(r"\bFINAL\b", in_types={"response"}),
    stop_signal("agente declaró cierre"),
)
```

Si querés precisión apuntando a un campo específico:

```python
def when_response_contains(pattern: str):
    rx = re.compile(pattern)
    def cond(history):
        for e in history.by_type("response"):
            if rx.search(e.content.get("text", "")):
                return True
        return False
    return cond
```

### Action simple

```python
def alert_now(history):
    history.append(author="orchestrator", type="alert",
                   content={"message": "algo pasó"})
```

### Action con parámetros (factory)

```python
def log_to_file(path):
    def action(history):
        path.write_text(history.to_json())
    return action

monitor.add_rule(when_more_than(100), log_to_file(Path("/tmp/dump.json")))
```

### Action que llama a un agente externo

```python
def critic_review(critic_agent):
    def action(history):
        text = history.export("agent_default")
        critique = critic_agent.run(f"criticá: {text}")
        history.append(author="critic", type="critique",
                       content={"text": critique})
    return action

monitor.add_rule(every_n_steps(10), critic_review(critic_agent))
```

---

## "Guardar" un monitor

Como las reglas son funciones (closures), no son nativamente serializables. La librería no provee `monitor.save()` / `Monitor.load()`.

Para reusar un monitor entre runs o módulos, definilo en código como **factory** o instancia a nivel módulo:

```python
# my_monitors.py
from instantneo.monitor import Monitor
from instantneo.actions import stop_signal, append_note
from instantneo.conditions import when_type_present, every_n_steps

def build_standard_monitor():
    """Factory que arma el monitor estándar para mis runs."""
    m = Monitor(name="standard")
    m.add_rule(when_type_present("error"), stop_signal("err"))
    m.add_rule(every_n_steps(10),          append_note("checkpoint"))
    return m
```

```python
# main.py
from my_monitors import build_standard_monitor

monitor = build_standard_monitor()
loop = InstantLoop(agent=A, history=history, monitors=monitor)
```

---

## Cómo lo usa un Loop

El `InstantLoop` (ver `loop-design.md`) acepta `monitors=` en su constructor con el mismo patrón que `InstantNeo(tools=...)`:

```python
# Caso 1: una instance
loop = InstantLoop(agent=A, history=H, monitors=my_monitor)

# Caso 2: lista (se unen vía MonitorOperations.union internamente)
loop = InstantLoop(agent=A, history=H, monitors=[mon_a, mon_b])

# Caso 3: nada
loop = InstantLoop(agent=A, history=H)
# loop.monitor es Monitor() vacío
```

El Loop **invoca su monitor una vez por step**, al final, después de que el agente y el bridge appendearon sus entries. Esa cadencia es la del Loop — el Monitor mismo no tiene reloj.

---

## Uso sin Loop

El Monitor es independiente del Loop. Sirve igual contra cualquier History:

```python
# Análisis post-hoc — un history terminado, miro qué pasó
history = History.from_dicts(json.load(open("run.json")))
m = Monitor()
m.add_rule(when_type_present("error"), append_note("encontré errores"))
m(history)              # una pasada
```

```python
# Monitoreo manual — voy appendeando y evaluando entre medio
history = History()
m = Monitor()
m.add_rule(every_n_appends(10), my_action)

for thing in stream:
    history.append(author="...", type="...", content={...})
    m(history)          # vos decidís cuándo
```

```python
# Polling en background (patrón opt-in)
import threading, time

stop = threading.Event()

def watcher():
    while not stop.is_set():
        m(history)
        time.sleep(1.0)

threading.Thread(target=watcher, daemon=True).start()
# ... cuando termines:
stop.set()
```

El último patrón solo conviene para actions out-of-band (notify, persist) y asume que vas a manejar locking en `history.append` si el History se modifica concurrentemente.

---

## Ejemplos completos

### Parar si aparece un error

```python
from instantneo.conditions import when_type_present
from instantneo.actions import stop_signal

monitor.add_rule(when_type_present("error"), stop_signal("se detectó un error"))
```

### Notificar a Slack cuando aparece un error (out-of-band custom)

```python
import requests

def notify_slack(webhook_url):
    def action(history):
        last_err = history.by_type("error")[-1]
        requests.post(webhook_url, json={"text": f"Error: {last_err.content['exception']}"})
    return action

monitor.add_rule(when_type_present("error"), notify_slack("https://hooks.slack.com/..."))
```

### Persistir el History a disco cada N entries

```python
from pathlib import Path

def persist_to_disk(path):
    def action(history):
        path.write_text(history.to_json())
    return action

monitor.add_rule(every_n_appends(50), persist_to_disk(Path("session.json")))
```

### Monitor compartido entre dos Loops sobre el mismo History

```python
shared = Monitor(name="shared")
shared.add_rule(when_type_present("error"), stop_signal("err"))

history = History()
loop_A = InstantLoop(agent=A, history=history, monitors=shared)
loop_B = InstantLoop(agent=B, history=history, monitors=shared)
# Ambos Loops invocan la misma instancia de Monitor. Mutarla afecta a los dos.
```

### Composición de monitors temáticos

```python
audit_monitor = Monitor(name="audit")
audit_monitor.add_rule(every_n_steps(10), write_progress(run_dir))

alert_monitor = Monitor(name="alerts")
alert_monitor.add_rule(when_type_present("error"), notify_slack(webhook))

loop = InstantLoop(agent=A, history=history, monitors=[audit_monitor, alert_monitor])
# loop.monitor es la unión (snapshot estático)
```

---

## Verificación (cuando se implemente)

Tests del Monitor:

- `test_monitor_constructor_with_optional_name`
- `test_add_rule_appends_to_internal_list`
- `test_call_fires_when_condition_true`
- `test_call_skips_when_condition_false`
- `test_rules_run_in_registration_order`
- `test_action_appends_visible_to_subsequent_rules_in_same_call`
- `test_monitor_is_callable_as_function`

Tests de `MonitorOperations.union`:

- `test_union_combines_rules_in_registration_order`
- `test_union_does_not_mutate_inputs`

Tests de conditions built-in (uno por cada): `when_entry_count_above`, `when_type_count_above`, `when_author_count_above`, `when_type_present`, `when_last_is_type`, `when_last_is_author`, `when_last_content_matches`, `when_tokens_above` (default y custom tokenizer), `every_n_steps`, `at_step`, `And`/`Or`/`Not`.

Tests de actions built-in: `stop_signal`, `append_note`.

---

## Pendiente (a documentar en próximas vueltas)

- **Layout final** de los módulos: si `conditions` y `actions` viven en archivos separados o agrupados en `instantneo/utils.py`.
- **Helpers de queries** (`current_run_id`, `current_origin`, `current_step_num`): viven en `instantneo/history/queries.py` y son consumidos por las built-in actions y por las custom del usuario. Documentación detallada en `loop-design.md`.
