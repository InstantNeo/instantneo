# Monitor — diseño y API

Documento de la capa que **observa** el History y **reacciona** cuando se cumplen condiciones registradas. Vive en composición con History (cada instancia de History tiene su Monitor asociado).

---

## Idea central

Un `Monitor` es el objeto que mira un History y dispatcha **reglas** cuando las condiciones se cumplen. Las reglas son pares `(when, do)` donde:

- `when` es una **condición** — función pura `Callable[[History], bool]`.
- `do` es una **acción** — función `Callable[[History], None]`, típicamente appendea entries.

El Monitor NO se evalúa solo. Alguien (típicamente el Loop) llama `monitor.evaluate()` en momentos definidos. En esa llamada, el Monitor itera sus reglas en orden y dispara las que matchean.

**Reglas que sostienen el diseño:**

- Cada Monitor está atado a UNA instancia de History (composición, no objeto suelto).
- El History es pasivo: no notifica al Monitor. El Monitor consulta el History cuando le piden `evaluate()`.
- Las funciones `when` y `do` reciben el History entero (acceso completo al API).
- Por default, todo es **síncrono**: las acciones bloquean el `evaluate()` hasta completarse.

---

## Cómo se crea

No se crea directamente. Cada `History()` instancia un `Monitor` internamente y lo expone como atributo:

```python
history = History()
history.monitor    # ya existe, Monitor vacío
```

Para registrar reglas:

```python
history.monitor.on(every_n_steps(5),    summarize_with(M))
history.monitor.on(when_type_present("error"), stop_with("error en step"))
```

---

## API de `Monitor`

```python
class Monitor:
    def __init__(self, history: "History"):
        self._history = history
        self._rules: list[tuple[Condition, Action, str | None]] = []

    def on(self, when: Condition, do: Action, name: str | None = None) -> None:
        """Registra una regla. El name es opcional, útil para logging."""

    def evaluate(self) -> None:
        """Itera reglas y dispara las que matchean. Llamado por el orquestador."""

    def list_rules(self) -> list[str | None]:
        """Nombres (o None) de las reglas registradas, en orden."""

    def clear(self) -> None:
        """Quita todas las reglas."""
```

Cuatro métodos. Sin `off`, `disable`, `priority`, etc. — agregables si aparece la necesidad real.

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

- **Conditions** deben ser puras. Misma history → mismo bool. Sin side effects, sin I/O. Si una condition appendea o muta, los logs mienten y la regla puede dispararse dos veces.
- **Actions** son intencionalmente impuras. Producen efectos: appendear entries (lo más común), llamar a un LLM, escribir a disco, hacer HTTP.

### Sincronía

`evaluate()` corre las reglas **secuencialmente** en el orden registrado. Cada action **bloquea** hasta terminar:

- Si una action llama a un LLM que tarda 10 segundos, el siguiente step del Loop espera 10 segundos.
- Las acciones posteriores ven el estado dejado por las anteriores en el mismo `evaluate()`.

Si necesitás no bloquear (notificaciones laterales), tu action puede disparar un thread/task y retornar — pero las entries que produzca llegarán fuera de orden respecto al step.

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

`predicate` es un `Callable[[dict], bool]` que recibe el `content` y devuelve bool. Útil para chequeos de contenido sin escribir una condition entera:

```python
when_last_content_matches(lambda c: "FINAL:" in c.get("text", ""))
```

### Sobre tokens (asume una vista registrada)

| Función | Qué hace |
|---|---|
| `when_tokens_above(view_name, n, tokenizer=None)` | El output de `history.export(view_name)` supera `n` tokens |

`tokenizer` es opcional. Default: estimación rápida basada en chars (`len(text) // 4`). Pasale uno preciso si te importa la exactitud:

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

```python
history.monitor.on(
    And(every_n_steps(5), when_tokens_above("agent_default", 50_000)),
    summarize_with(M),
)
```

---

## Actions built-in

Set chico también. La mayoría de las acciones útiles son específicas del dominio del usuario; mejor que las escriba inline.

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

history.monitor.on(when_more_than(50), my_action)
```

### Action simple

```python
def alert_now(history):
    history.append(author="orchestrator", type="alert",
                   content={"message": "algo pasó"})
```

### Action con parámetros (factory)

```python
def log_to_file(path: Path):
    def action(history):
        path.write_text(history.to_json())
    return action

history.monitor.on(when_more_than(100), log_to_file(Path("/tmp/dump.json")))
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

history.monitor.on(every_n_steps(10), critic_review(critic_agent))
```

---

## Ejemplos completos

### Compactar contexto cuando crece

```python
from instantneo.history import History
from instantneo.conditions import when_tokens_above
from instantneo.actions import summarize_with

history = History()
history.monitor.on(
    when_tokens_above("agent_default", 100_000),
    summarize_with(M, view_name="agent_default"),
)
```

### Parar si aparece un error

```python
from instantneo.conditions import when_type_present
from instantneo.actions import stop_with

history.monitor.on(
    when_type_present("error"),
    stop_with("se detectó un error en algún step"),
)
```

### Resumen periódico cuando además los tokens están altos

```python
from instantneo.conditions import every_n_steps, And, when_tokens_above
from instantneo.actions import summarize_with

history.monitor.on(
    And(every_n_steps(5), when_tokens_above("agent_default", 50_000)),
    summarize_with(M),
)
```

### Abort tardío si todo falla

```python
history.monitor.on(
    when_tokens_above("agent_default", 200_000),
    stop_with("contexto irrecuperable"),
)
```

### Custom: alerta si M no apareció hace muchos turnos

```python
def when_M_silent_for(n: int):
    def cond(history):
        m_entries = history.by_author("M")
        if not m_entries:
            return True
        return history.all()[-1].id - m_entries[-1].id > n
    return cond

def alert_M_silent(history):
    history.append(author="orchestrator", type="alert",
                   content={"about": "M ausente hace mucho"})

history.monitor.on(when_M_silent_for(20), alert_M_silent)
```

---

## Verificación (cuando se implemente)

Tests del Monitor, sin orquestador:

- `test_monitor_created_with_history`
- `test_on_registers_rule`
- `test_evaluate_fires_when_condition_true`
- `test_evaluate_skips_when_condition_false`
- `test_rules_run_in_registration_order`
- `test_action_appends_visible_to_subsequent_rules_in_same_evaluate`
- `test_clear_removes_all_rules`
- `test_list_rules_returns_names_in_order`

Tests de conditions built-in (uno por cada):

- `test_when_entry_count_above`
- `test_when_type_count_above`
- `test_when_author_count_above`
- `test_when_type_present`
- `test_when_last_is_type` / `test_when_last_is_author` / `test_when_last_content_matches`
- `test_when_tokens_above_default_estimator`
- `test_when_tokens_above_custom_tokenizer`
- `test_every_n_steps_with_step_start_entries`
- `test_at_step_with_step_start_entries`
- `test_combinators_and_or_not`

Tests de actions built-in:

- `test_stop_with_appends_stop_signal`
- `test_summarize_with_appends_summary_entry_with_refs`
- `test_append_note_appends_note`

---

## Pendiente (a documentar en próximas vueltas)

- **Loop**: cómo invoca `history.monitor.evaluate()` en su flujo y cómo lee `stop_signal` para romper.
- **Bridge** `run_info_to_entries`: types canónicos producidos por el bridge desde `RunInfo` (`response`, `tool_call`).
- **Layout final** de los módulos: si `conditions` y `actions` viven en archivos separados (`instantneo/conditions.py`, `instantneo/actions.py`) o agrupados en `instantneo/utils.py`. Decisión cuando aterricemos la implementación.
