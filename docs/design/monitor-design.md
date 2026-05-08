# Monitor — diseño y API

Documento de la capa que **observa** un History y **reacciona** cuando se cumplen condiciones registradas. Vive como objeto standalone, attachable a uno o varios Histories.

---

## Idea central

Un `Monitor` es un objeto que tiene **reglas**: pares `(when, do)` donde:

- `when` es una **condición** — función pura `Callable[[History], bool]`.
- `do` es una **acción** — función `Callable[[History], None]`, típicamente appendea entries.

El Monitor NO se evalúa solo. Alguien (típicamente un Loop) llama `monitor.evaluate(history)` en momentos definidos. En esa llamada, el Monitor itera sus reglas en orden y dispara las que matchean.

**Reglas que sostienen el diseño:**

- El Monitor es **standalone**: existe sin necesidad de un History específico. Se le pasa el history al evaluar.
- **Reusable**: la misma instancia puede attacharse a múltiples Histories (compartiendo reglas).
- Por default, todo es **síncrono**: las acciones bloquean la `evaluate()` hasta completarse.
- No hay registry global, no hay events del History al Monitor. El Monitor consulta el History cuando lo llaman.

---

## API de `Monitor`

```python
class Monitor:
    def __init__(self, name: str | None = None):
        self.name = name
        self._rules: list[tuple[Condition, Action]] = []

    def register_rule(self, when: Condition, do: Action) -> None:
        """Añade una regla (when, do) al final de la lista."""

    def evaluate(self, history: "History") -> None:
        """Itera reglas y dispara las que matchean contra el history pasado."""
```

Dos métodos públicos. `name` es opcional (debug, identificación).

---

## Cómo se crea y se inserta en un History

Construcción explícita:

```python
from instantneo.monitor import Monitor

monitor = Monitor()
monitor.register_rule(when_tokens_above("agent_default", 100_000), summarize_with(M))
monitor.register_rule(when_type_present("error"),                  stop_with("err"))
```

Inserción en un History (mismo pattern que `InstantNeo(tools=...)`):

```python
# Caso 1: una instancia
history = History(monitors=monitor)
# history.monitor IS monitor (mismo objeto; mutaciones se propagan)

# Caso 2: lista de monitors (se unen)
history = History(monitors=[monitor_a, monitor_b])
# history.monitor es un nuevo Monitor con las reglas de ambos (snapshot)

# Caso 3: nada
history = History()
# history.monitor es Monitor() vacío (default)
```

`history.monitor` **siempre existe**. Para ergonomía, History expone proxies:

```python
history.register_rule(when, do)        # equivale a history.monitor.register_rule(when, do)
history.evaluate_monitor()             # equivale a history.monitor.evaluate(history)
```

---

## `MonitorOperations.union`

Para combinar varios monitors en uno:

```python
class MonitorOperations:
    @staticmethod
    def union(*monitors: Monitor, name: str | None = None) -> Monitor:
        """Combina N monitors en uno nuevo, preservando orden de reglas."""
```

`History` lo usa internamente cuando le pasás una lista al constructor. También importable para usos manuales.

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
- Appendear nuevas entries: `history.append(...)` — esto es lo que casi siempre hace una action.
- Serializar: `history.to_json()`, `history.to_dicts()`.

### Pureza

- **Conditions** deben ser puras. Misma history → mismo bool. Sin side effects, sin I/O.
- **Actions** son intencionalmente impuras. Producen efectos: appendear entries, llamar a un LLM, escribir a disco, hacer HTTP.

### Sincronía

`evaluate()` corre las reglas **secuencialmente** en el orden registrado. Cada action **bloquea** hasta terminar. Las acciones posteriores ven el estado dejado por las anteriores en el mismo `evaluate()`.

Si necesitás no bloquear, tu action puede disparar un thread/task y retornar — pero las entries que produzca llegarán fuera de orden respecto al step.

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

## Actions built-in

| Función | Qué hace |
|---|---|
| `stop_with(reason)` | Appendea `Entry(type="stop_signal", content={"reason": reason})`. El Loop la lee y rompe |
| `summarize_with(agent_M, view_name="agent_default")` | Ejecuta `agent_M` sobre `history.export(view_name)`, appendea `Entry(type="summary", refs=..., content={"text": ...})` cubriendo entries de `response`/`tool_call` no cubiertas previamente |
| `append_note(text, author="orchestrator")` | Appendea `Entry(type="note", content={"text": text})` |

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

monitor.register_rule(when_more_than(50), my_action)
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

monitor.register_rule(
    when_any_content_matches(r"\bFINAL\b", in_types={"response"}),
    stop_with("agente declaró cierre"),
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

monitor.register_rule(when_more_than(100), log_to_file(Path("/tmp/dump.json")))
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

monitor.register_rule(every_n_steps(10), critic_review(critic_agent))
```

---

## "Guardar" un monitor

Como las reglas son funciones (closures), no son nativamente serializables. La librería no provee `monitor.save()` / `Monitor.load()`.

Para reusar un monitor entre runs o módulos, definilo en código como **factory** o instancia a nivel módulo:

```python
# my_monitors.py
from instantneo.monitor import Monitor
from instantneo.actions import summarize_with, stop_with
from instantneo.conditions import when_tokens_above, when_type_present

def build_standard_monitor(summarizer_agent):
    """Factory que arma el monitor estándar para mis runs."""
    m = Monitor(name="standard")
    m.register_rule(when_tokens_above("agent_default", 100_000),
                    summarize_with(summarizer_agent))
    m.register_rule(when_type_present("error"), stop_with("err"))
    return m
```

```python
# main.py
from my_monitors import build_standard_monitor

monitor = build_standard_monitor(my_M)
history = History(monitors=monitor)
```

---

## Ejemplos completos

### Compactar contexto cuando crece

```python
from instantneo.history import History
from instantneo.monitor import Monitor
from instantneo.conditions import when_tokens_above
from instantneo.actions import summarize_with

monitor = Monitor()
monitor.register_rule(when_tokens_above("agent_default", 100_000), summarize_with(M))

history = History(monitors=monitor)
```

### Parar si aparece un error

```python
from instantneo.conditions import when_type_present
from instantneo.actions import stop_with

monitor.register_rule(when_type_present("error"), stop_with("se detectó un error"))
```

### Resumen periódico cuando además los tokens están altos

```python
from instantneo.conditions import every_n_steps, And, when_tokens_above
from instantneo.actions import summarize_with

monitor.register_rule(
    And(every_n_steps(5), when_tokens_above("agent_default", 50_000)),
    summarize_with(M),
)
```

### Monitor compartido entre dos histories

```python
shared = Monitor(name="shared")
shared.register_rule(when_type_present("error"), stop_with("err"))

history_a = History(monitors=shared)
history_b = History(monitors=shared)
# Ambas usan la misma instancia. Registrar otra regla en shared se propaga a las dos.
```

### Composición de monitors temáticos

```python
context_monitor = Monitor(name="context")
context_monitor.register_rule(when_tokens_above("default", 100_000), summarize_with(M))

audit_monitor = Monitor(name="audit")
audit_monitor.register_rule(every_n_steps(10), write_progress(run_dir))

history = History(monitors=[context_monitor, audit_monitor])
# history.monitor es la unión (snapshot estático)
```

---

## Verificación (cuando se implemente)

Tests del Monitor:

- `test_monitor_constructor_with_optional_name`
- `test_register_rule_appends_to_internal_list`
- `test_evaluate_fires_when_condition_true`
- `test_evaluate_skips_when_condition_false`
- `test_rules_run_in_registration_order`
- `test_action_appends_visible_to_subsequent_rules_in_same_evaluate`

Tests de `MonitorOperations.union`:

- `test_union_combines_rules_in_registration_order`
- `test_union_does_not_mutate_inputs`

Tests de attachment a History:

- `test_history_default_has_empty_monitor`
- `test_history_with_single_monitor_uses_same_instance`
- `test_history_with_list_of_monitors_uses_union`
- `test_history_register_rule_proxies_to_monitor`
- `test_history_evaluate_monitor_calls_monitor_evaluate_with_self`

Tests de conditions built-in (uno por cada): `when_entry_count_above`, `when_type_count_above`, `when_author_count_above`, `when_type_present`, `when_last_is_type`, `when_last_is_author`, `when_last_content_matches`, `when_tokens_above` (default y custom tokenizer), `every_n_steps`, `at_step`, `And`/`Or`/`Not`.

Tests de actions built-in: `stop_with`, `summarize_with`, `append_note`.

---

## Pendiente (a documentar en próximas vueltas)

- **Loop**: cómo invoca `history.evaluate_monitor()` en su flujo y cómo lee `stop_signal` para romper.
- **Bridge** `run_info_to_entries`: types canónicos producidos desde `RunInfo` (`response`, `tool_call`).
- **Layout final** de los módulos: si `conditions` y `actions` viven en archivos separados o agrupados en `instantneo/utils.py`.
