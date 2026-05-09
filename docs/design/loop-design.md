# Loop — diseño y API

Documento del **InstantLoop**, el orquestador concreto que corre un agente InstantNeo en un loop multi-step usando History + Monitor + bridge `append_entry_from_run`. Reemplaza el `instant_loop.py` actual con un diseño que aprovecha la arquitectura event-sourced.

---

## Idea central

El Loop ejecuta un agente InstantNeo en `N` steps consecutivos. Cada step:

1. Materializa la vista del History para construir el prompt del agente.
2. Invoca `agent.run(prompt)`.
3. Descompone el `RunInfo` resultante en entries vía el bridge.
4. Emite las entries operacionales del step (`step_start`, `step_end`).
5. Llama `history.evaluate_monitor()` para que las reglas registradas reaccionen.
6. Chequea `stop_signal` para decidir si seguir.

Termina cuando: alguna acción del Monitor appendea un `stop_signal`, se agota `max_steps`, o el agente crashea de forma irrecuperable.

**Reglas del diseño:**

- El Loop **es el dueño** de las entries operacionales (`run_start`, `step_start`, `step_end`, `error`, `stop_signal`, `run_end`). El bridge no las emite.
- El Loop **no muta** el History de otra forma que no sea `history.append(...)`.
- El Loop **invoca** al Monitor; no lo posee. El Monitor vive en `history.monitor`.
- El Loop **registra** una vista default `loop_default` al construirse, que el agente consume si no se especifica otra.

---

## API de `InstantLoop`

```python
from typing import Callable, Optional
from instantneo import InstantNeo
from instantneo.history import History


class InstantLoop:
    def __init__(
        self,
        *,
        agent: InstantNeo,
        history: Optional[History] = None,
        view: str = "loop_default",
        max_steps: int = 30,
        tools_for_step: Optional[Callable[[int, History], list]] = None,
        debug: bool = False,
    ):
        ...

    def run(self, prompt: str) -> RunResult:
        ...
```

### Parámetros

| Param | Tipo | Default | Rol |
|---|---|---|---|
| `agent` | `InstantNeo` | requerido | El agente que el Loop ejecuta en cada step |
| `history` | `History | None` | `None` (crea uno) | El History al que se appendea. Si es None, el Loop instancia uno propio. Si se pasa uno existente, el Loop lo reutiliza (multi-run sobre el mismo History) |
| `view` | `str` | `"loop_default"` | Nombre de la vista que el agente consume para construir su prompt cada turno |
| `max_steps` | `int` | `30` | Límite duro de steps |
| `tools_for_step` | `Callable[[int, History], list] | None` | `None` | Si se pasa, el Loop la llama antes de cada agent.run() para resolver qué tools están disponibles ese step. Si es None, usa todas las tools del agente |
| `debug` | `bool` | `False` | Si True, además de las entries normales el Loop emite `llm_debug` con `messages_sent` literal por turno |

### `RunResult`

```python
@dataclass
class RunResult:
    history:           History
    run_id:            str
    terminated_reason: str           # "stop_signal" | "max_steps" | "error"
    duration_s:        float
    total_steps:       int           # cuántos steps efectivamente corrieron
```

Acceso al detalle: vía `result.history.all()`, `result.history.export(view_name)`, `result.history.by_type(...)`. El `RunResult` es solo metadata del run completo.

---

## Vista `loop_default` (registrada al construir el Loop)

El Loop, al instanciarse, registra una vista llamada `loop_default` en su `History` si no existe ya con ese nombre. Esa vista es lo que el agente recibe como prompt en cada turno.

**Comportamiento de `loop_default`:**

```python
def loop_default(history: History) -> str:
    """Vista que el Loop le da al agente por default.

    Filtra entries operacionales y formatea como markdown.
    """
    entries = history.all()

    # Solo narrativos: el agente no necesita ver step_start, step_end, errors operacionales,
    # stop_signals, run_start, run_end, llm_debug.
    narrative_types = {"prompt", "response", "tool_call", "summary", "note", "redaction"}
    entries = [e for e in entries if e.type in narrative_types]

    return _markdown_format(entries)   # implementación en utils
```

Donde `_markdown_format` produce un texto compatible con lo que el `instant_loop.py` actual genera, para mantener backwards compat con consumers existentes (sistema de evals, etc.).

**Override por el user:** si se quiere otra vista, el user la registra antes de pasar el History al Loop:

```python
@history.view("loop_default")
def my_custom_default(history):
    ...   # mi versión

loop = InstantLoop(agent=A, history=history)   # usa la mía
```

O usa otro nombre y lo pasa al constructor:

```python
@history.view("for_a_special")
def for_a_special(history):
    ...

loop = InstantLoop(agent=A, history=history, view="for_a_special")
```

**Reasoning incluido por default**: `loop_default` debería renderizar el `reasoning` del response (si existe) como un bloque distinguible del texto. Importante para Anthropic extended thinking.

---

## Entries operacionales que emite el Loop

Todas con `author="orchestrator"`. Cada una tiene `content["run_id"]` para identificar el run en Histories multi-run.

### `run_start`

Emitida una vez al inicio de `loop.run()`. Concentra TODA la cabecera (config del agente + config del Loop) para reproducibilidad.

```python
content = {
    "run_id":     str,                     # uuid generado para este run
    "started_at": str,                     # ISO 8601 UTC

    "agent": {
        "name":       str,                  # agent.name si existe, sino "agent"
        "provider":   str,
        "model":      str,                  # default del agente
        "role_setup": str,                  # system prompt
        "tools":      list[str],            # nombres de las tools registradas
        "defaults": {                       # de InstantNeoParams, sin secrets
            "temperature":       float | None,
            "max_tokens":        int | None,
            "presence_penalty":  float | None,
            "frequency_penalty": float | None,
            "stop":              str | list | None,
            "seed":              int | None,
            "stream":            bool,
            "image_detail":      str,
        },
    },

    "loop": {
        "max_steps":     int,
        "view":          str,                # nombre de la vista usada
        "monitor_rules": list[str],          # nombres de reglas registradas en history.monitor (si tienen)
        "debug":         bool,
    },
}
```

**Lo que NO incluye**: `api_key`, `service_account_file`, `location`, schemas detallados de tools (solo nombres), versión de la lib (eso a logs).

### `prompt` del usuario

Emitida después del `run_start`, una vez por `loop.run()`, antes del primer step. Captura el prompt que el caller pasó.

```python
Entry(
    author="user",
    type="prompt",
    content={
        "text":   str,                      # el prompt
        "images": list[dict] | None,        # si hubo imágenes (referencias, ya procesadas)
        "run_id": str,
    },
)
```

### `step_start`

Emitida al inicio de cada step.

```python
content = {
    "run_id":          str,
    "step_num":        int,                 # 1-indexed
    "tools_available": list[str] | None,    # nombres de tools resueltas para este step
                                            # (None si no hubo gating)
}
```

### `step_end`

Emitida al final de cada step, después de evaluar el Monitor pero antes del próximo `step_start`.

```python
content = {
    "run_id":      str,
    "step_num":    int,
    "duration_ms": float,                   # tiempo del step completo (incluye agent.run + monitor)
}
```

### `error` (operacional, si el agente crasheó)

El bridge emite la entry `error` cuando `run_info.error` está poblado. Eso ya está cubierto por `append_entry_from_run`. El Loop no emite `error` adicionales — captura excepciones, las pone en `run_info.error` (vía el catch de InstantNeo) y deja que el bridge las plasme.

Si una excepción ocurriera fuera del `agent.run()` (e.g., en una action del Monitor), el Loop la atrapa y emite manualmente:

```python
content = {
    "run_id":        str,
    "step_num":      int,
    "exception":     str,
    "exception_type": str,                  # type(e).__name__
    "context":       str,                   # "monitor_action", "tools_for_step", etc.
}
```

### `stop_signal`

NO la emite el Loop. La emiten **acciones registradas en el Monitor** (típicamente `stop_with(reason)`). El Loop solo la **lee** para decidir si parar:

```python
# El Loop, después de evaluate_monitor:
if any(e.type == "stop_signal" for e in history.all() if entry_belongs_to_this_run(e)):
    terminated_reason = "stop_signal"
    break
```

Shape esperado de la entry (definido en `monitor-design.md`):

```python
content = {
    "reason": str,
    # eventualmente, run_id si la action lo agrega
}
```

### `run_end`

Emitida al cierre de `loop.run()`, sin importar la razón de terminación.

```python
content = {
    "run_id":            str,
    "completed_at":      str,
    "duration_s":        float,
    "terminated_reason": str,                # "stop_signal" | "max_steps" | "error"
    "total_steps":       int,                # cuántos steps corrieron
}
```

### `llm_debug` (solo si `debug=True`)

Si el Loop fue construido con `debug=True`, emite además, después de `append_entry_from_run`, una entry con info pesada:

```python
content = {
    "run_id":        str,
    "step_num":      int,
    "messages_sent": list[dict],             # el messages_sent literal del agente
}
```

Esta entry queda fuera de la vista `loop_default` (filtrada por su selector). Está disponible para debug profundo y reproducibilidad ultra-fiel.

---

## Flujo de `run()` paso a paso

```python
def run(self, prompt: str) -> RunResult:
    run_id = uuid.uuid4().hex
    started_at = time.time()
    terminated_reason = None
    total_steps = 0

    # 1. Asegurar que la vista exista
    if not self.history.has_view(self.view):
        self.history.add_view(self.view, _build_loop_default_view())

    # 2. Emitir run_start con toda la cabecera
    self.history.append(
        author="orchestrator",
        type="run_start",
        content=self._build_run_start_content(run_id, started_at),
    )

    # 3. Emitir el prompt del user
    self.history.append(
        author="user",
        type="prompt",
        content={
            "text":   prompt,
            "images": _refs_from(self.agent.config.images),
            "run_id": run_id,
        },
    )

    # 4. Loop de steps
    for step_num in range(1, self.max_steps + 1):
        step_start_time = time.perf_counter()

        # 4.a Resolver tools de este step
        tools = (
            self.tools_for_step(step_num, self.history)
            if self.tools_for_step
            else None  # None = todas las del agente
        )

        # 4.b step_start
        self.history.append(
            author="orchestrator",
            type="step_start",
            content={
                "run_id":          run_id,
                "step_num":        step_num,
                "tools_available": [t.name for t in tools] if tools else None,
            },
        )

        # 4.c Render del prompt vía vista
        rendered = self.history.export(self.view)

        # 4.d agent.run() — captura excepciones a nivel run
        try:
            if tools is not None:
                # Reemplazar temporalmente las tools del agente
                self.agent.run(rendered, tools=tools)   # asume que run() acepta tools=
            else:
                self.agent.run(rendered)
        except Exception as e:
            # Si es excepción a nivel run, append_entry_from_run la capta de last_run.error
            # Si no es captada por InstantNeo, la registramos manualmente:
            if self.agent.last_run is None or self.agent.last_run.error is None:
                self.history.append(
                    author="orchestrator",
                    type="error",
                    content={
                        "run_id":         run_id,
                        "step_num":       step_num,
                        "exception":      str(e),
                        "exception_type": type(e).__name__,
                        "context":        "agent.run",
                    },
                )
                terminated_reason = "error"
                break

        # 4.e Bridge: descomponer last_run en entries
        append_entry_from_run(
            self.history,
            self.agent.last_run,
            turn_num=step_num,
            author=self.agent.name or "agent",
        )

        # 4.f Si debug, capturar messages_sent literal
        if self.debug and self.agent.last_run:
            self.history.append(
                author="orchestrator",
                type="llm_debug",
                content={
                    "run_id":        run_id,
                    "step_num":      step_num,
                    "messages_sent": self.agent.last_run.messages_sent,
                },
            )

        # 4.g step_end
        self.history.append(
            author="orchestrator",
            type="step_end",
            content={
                "run_id":      run_id,
                "step_num":    step_num,
                "duration_ms": (time.perf_counter() - step_start_time) * 1000,
            },
        )

        # 4.h Evaluar Monitor (sus actions pueden appendear stop_signal, summaries, etc.)
        try:
            self.history.evaluate_monitor()
        except Exception as e:
            self.history.append(
                author="orchestrator",
                type="error",
                content={
                    "run_id":         run_id,
                    "step_num":       step_num,
                    "exception":      str(e),
                    "exception_type": type(e).__name__,
                    "context":        "monitor_action",
                },
            )
            terminated_reason = "error"
            break

        # 4.i Chequear stop_signal de este run
        if any(
            e.type == "stop_signal" and e.content.get("run_id") == run_id
            for e in self.history.all()
        ):
            terminated_reason = "stop_signal"
            total_steps = step_num
            break

        total_steps = step_num

    # 5. Determinar razón si no se rompió antes
    if terminated_reason is None:
        terminated_reason = "max_steps"

    # 6. run_end
    completed_at = time.time()
    self.history.append(
        author="orchestrator",
        type="run_end",
        content={
            "run_id":            run_id,
            "completed_at":      datetime.fromtimestamp(completed_at, tz=timezone.utc).isoformat(),
            "duration_s":        completed_at - started_at,
            "terminated_reason": terminated_reason,
            "total_steps":       total_steps,
        },
    )

    return RunResult(
        history=self.history,
        run_id=run_id,
        terminated_reason=terminated_reason,
        duration_s=completed_at - started_at,
        total_steps=total_steps,
    )
```

---

## Helpers necesarios

### `current_run_config(history) -> dict | None`

Devuelve el `content` de la entry `run_start` más reciente, o `None`. Útil para que conditions/actions del Monitor accedan a la cabecera sin escarbar.

```python
def current_run_config(history):
    starts = history.by_type("run_start")
    return starts[-1].content if starts else None
```

Vive en `instantneo/history/queries.py`.

### `current_run_id(history) -> str | None`

Idem, devolviendo solo el `run_id`.

### `current_step_num(history) -> int | None`

Devuelve el `step_num` del `step_start` más reciente del run actual. Lo necesitan conditions tipo `every_n_steps`.

---

## Integración con Monitor

El Loop NO crea ni gestiona el Monitor. Lo hereda del `History`. Si el caller construye el History con monitors, esos monitors se ejecutan en cada `evaluate_monitor()`:

```python
monitor = Monitor()
monitor.register_rule(every_n_steps(5),         summarize_with(M))
monitor.register_rule(when_type_present("error"), stop_with("err"))

history = History(monitors=monitor)
loop = InstantLoop(agent=A, history=history, max_steps=30)

loop.run("investigá X")
# Cada step, después del bridge, history.monitor evalúa sus reglas.
# Si alguna registra stop_signal, el Loop rompe.
```

Si no se pasa `history`, el Loop crea uno nuevo y vacío (sin reglas). El caller puede agregar reglas después en `loop.history.monitor.register_rule(...)`.

---

## Backwards compat con `instant_loop.py` actual

El `instant_loop.py` existente expone:

```python
loop = InstantLoop(
    agent,
    stop_tool="report_classification",
    max_turns=30,
    debug_dir=...,
    debug_run_dir=...,
    agent_config=...,
    images=...,
    image_detail=...,
)
result = loop.run(prompt)   # → {"result": dict, "trace": dict}
```

El nuevo Loop **no preserva esa API exactamente**. La migración es un cambio mayor por design (la arquitectura es nueva). Pero se puede mantener una capa de compat en un módulo separado:

```python
# instantneo/experimental/instant_loop_compat.py
class InstantLoop:
    """Wrapper backwards-compatible sobre el nuevo Loop."""
    def __init__(self, agent, stop_tool="...", max_turns=30,
                 debug_dir=None, agent_config=None, images=None, image_detail=None, **kwargs):
        self._impl = NewInstantLoop(
            agent=agent,
            max_steps=max_turns,
            debug=bool(debug_dir),
        )
        self._stop_tool = stop_tool
        self._debug_dir = debug_dir
        self._agent_config = agent_config

        # Registrar regla equivalente al stop_tool actual:
        # cuando el agente llama esta tool, parar el loop.
        self._impl.history.monitor.register_rule(
            when_last_tool_called(stop_tool),
            stop_with(f"agent called {stop_tool}"),
        )

    def run(self, prompt):
        result = self._impl.run(prompt)
        # Reconstruir el dict legacy {"result": ..., "trace": ...}
        return _build_legacy_dict(result)
```

Esa capa permite que el código existente que usa el loop viejo siga funcionando mientras la migración progresa.

---

## Layout

```
instantneo/
  history/
    history.py
    monitor.py
    from_run_info.py     # bridge append_entry_from_run
    queries.py           # current_run_config, current_run_id, current_step_num
    utils.py             # markdown_format y otros helpers
  loop/
    __init__.py          # re-exporta InstantLoop
    instant_loop.py      # la clase nueva
    default_view.py      # función _build_loop_default_view (loop_default)
  experimental/
    instant_loop.py      # versión actual, deprecated, mantiene API legacy
    instant_loop_compat.py   # capa backwards-compat opcional
```

---

## Verificación (cuando se implemente)

Tests del Loop con un agente fake (no requiere llamar al provider real):

- `test_loop_run_emits_run_start_with_full_config`
- `test_loop_run_emits_prompt_entry_after_run_start`
- `test_loop_run_emits_step_start_step_end_per_step`
- `test_loop_run_calls_append_entry_from_run_per_step`
- `test_loop_run_evaluates_monitor_per_step`
- `test_loop_stops_on_stop_signal`
- `test_loop_stops_on_max_steps_when_no_stop_signal`
- `test_loop_handles_run_error_via_bridge`
- `test_loop_emits_run_end_with_terminated_reason`
- `test_loop_default_view_filters_operational_entries`
- `test_loop_with_custom_view_uses_custom`
- `test_loop_with_tools_for_step_uses_callback`
- `test_loop_with_debug_emits_llm_debug_entries`
- `test_loop_with_existing_history_appends_run_start_per_run`   # multi-run

Tests de integración con un Monitor con reglas reales:

- `test_loop_with_monitor_summarize_every_n_appends_summary`
- `test_loop_with_monitor_stop_on_error_breaks_loop`
- `test_loop_with_combined_monitor_rules` (var rules registradas, todas evaluadas en orden)

---

## Pendiente / migración

### Pre-requisitos

1. **Fix de `reasoning_tokens` en InstantNeo** (PR independiente). Sin esto, el bridge produce `usage["reasoning_tokens"] = None` siempre.
2. **History + Monitor + bridge** documentados e implementados.

### Pasos

1. **PR del Loop nuevo**:
   - Implementar `InstantLoop` en `instantneo/loop/instant_loop.py`.
   - Implementar `_build_loop_default_view` y `_markdown_format`.
   - Implementar helpers `current_run_config`, `current_run_id`, `current_step_num` en `queries.py`.
   - Tests por componente.
   - Documentar en README cuando salga.

2. **PR de capa compat** (opcional, mismo PR o siguiente):
   - Wrapper que mapea API legacy → nueva.
   - Tests de regresión: el sistema de evals existente sigue funcionando con el wrapper.

3. **PR de migración interna**:
   - Migrar callers internos del `instant_loop.py` viejo al nuevo (vía wrapper o directo).
   - Marcar el viejo como deprecated.

4. **Eventualmente** (no en esta serie):
   - Eliminar el `instant_loop.py` viejo cuando todos los callers migraron.

### Decisiones abiertas para el momento de implementar

- **Tools per step**: hoy `agent.run()` no acepta `tools=` directamente — usa `self.capabilities`. La forma de "gating" tendría que ser:
  - (a) Mutar temporalmente `agent.capabilities` (frágil).
  - (b) Construir un agente clon con tools restringidas (caro).
  - (c) Modificar InstantNeo para aceptar `tools=` en `run()`.
  
  Decisión: la c. Pero requiere tocar InstantNeo. Si no se quiere abrir eso ahora, primer iteración del Loop no soporta `tools_for_step` (None siempre).

- **Concurrencia / async**: hoy todo es síncrono. Async support es feature futura, no bloquea el MVP del Loop.

- **Persistencia del History entre runs**: ya está soportada por el design (`History(monitors=...)` reutilizable). Subclases tipo `FileHistory` quedan como issue futura.

- **Imágenes en el prompt entry**: por ahora se appendean como están en `agent.config.images`. Si el caller pasa imágenes per-run via `run(images=...)`, hay que decidir si emitir un `prompt` distinto o modificar el `agent`. Decisión a tomar al implementar.
