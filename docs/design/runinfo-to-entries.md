# Bridge: `RunInfo` → entries del History

Documento del **bridge** que conecta lo que produce InstantNeo (`RunInfo` accesible vía `agent.last_run`) con el History event-sourced. Es la traducción que cualquier orquestador (Loop, Pipeline futuro) usa para registrar el resultado de una llamada al agente.

La pieza central es la función `append_entry_from_run`, vive en `instantneo/history/from_run_info.py`. No es una clase, no es un singleton — es una función pura que el orquestador llama una vez por turno.

---

## Propósito

Después de `agent.run(prompt)`, el agente populariza `agent.last_run: RunInfo` con todo lo que pasó: response, reasoning, tool calls ejecutadas, usage, timing, errores. El bridge descompone ese `RunInfo` en `Entry`s narrativos y operacionales y los appendea al History.

**Lo que mejora respecto al `instant_loop.py` actual:**

- Args y results de tools quedan **tipados** (dict, lista, valores nativos) en lugar de stringificados.
- Reasoning content del modelo queda **accesible**, no escondido en archivos de debug.
- Reasoning tokens (cuando el provider los da) entran al History.
- Provider, model, finish_reason, usage, timing quedan **estructurados por turno** en cada response entry.
- Errores per-tool y per-run quedan diferenciados en entries propios.

---

## Función `append_entry_from_run`

```python
from instantneo.history import History, Entry
from instantneo.models.run_info import RunInfo


def append_entry_from_run(
    history: History,
    run_info: RunInfo,
    *,
    turn_num: int,
    author: str,
    origin: str,
    run_id: str,
) -> list[Entry]:
    """Descompone un RunInfo en entries y las appendea al History.

    Genera, en orden:
      - 1 entry type='error' si run_info.error (y retorna).
      - 1 entry type='response' si run_info.response_content.
      - N entries type='tool_call', una por cada tool_execution.

    Cada entry generada lleva `origin` y `run_id` en su content para que
    el log sea filtrable por orquestador y por invocación.

    `origin` es genérico: si te llama un Loop, será `loop.name`; si te llama
    un Pipeline futuro, su nombre; si te llama un script manual, lo que el
    autor decida ("manual", "script_v2", etc.).

    Retorna las entries appendeadas en orden.
    """
    appended: list[Entry] = []

    # Run-level error: cancela el resto, una sola entry y sale.
    if run_info.error:
        appended.append(history.append(
            author=author,
            type="error",
            content={
                "exception":   run_info.error,
                "duration_ms": run_info.duration_ms,
                "provider":    run_info.provider,
                "model":       run_info.model,
                "origin":   origin,
                "run_id":      run_id,
                "turn_num":    turn_num,
            },
        ))
        return appended

    # Response (con reasoning si vino, ambos al mismo nivel)
    if run_info.response_content is not None:
        first_call = run_info.llm_calls[0] if run_info.llm_calls else None
        appended.append(history.append(
            author=author,
            type="response",
            content={
                "text":            run_info.response_content,
                "reasoning":       run_info.reasoning,
                "finish_reason":   run_info.finish_reason,
                "usage":           run_info.usage,
                "duration_ms":     run_info.duration_ms,
                "provider":        run_info.provider,
                "model":           run_info.model,
                "response_id":     getattr(first_call, "response_id", None),
                "response_model":  getattr(first_call, "response_model", None),
                "provider_timing": run_info.provider_timing,
                "origin":       origin,
                "run_id":          run_id,
                "turn_num":        turn_num,
            },
        ))

    # Tool calls (arguments y result intactos, sin extraer razonamiento)
    for te in run_info.tool_executions or []:
        appended.append(history.append(
            author=author,
            type="tool_call",
            content={
                "name":           te.name,
                "arguments":      te.arguments,
                "result":         te.result,
                "exception":      te.exception,
                "execution_mode": te.execution_mode,
                "origin":      origin,
                "run_id":         run_id,
                "turn_num":       turn_num,
            },
        ))

    return appended
```

**Características:**

- **Pura**: no muta el `RunInfo`. Solo lee y appendea.
- **Sin estado**: no recuerda invocaciones previas.
- **Reusable**: cualquier orquestador la llama después de `agent.run()`.
- **No conoce el orquestador**: no emite `step_start`, `step_end`, `run_start`, `run_end` ni `stop_signal`. Esos los emite el orquestador directamente cuando corresponde.

---

## Decisiones del shape de cada entry

### Entry `response`

```python
content = {
    "text":                str,             # run_info.response_content
    "reasoning":           str | None,       # run_info.reasoning (thinking del modelo)
    "finish_reason":       str,              # "stop", "tool_calls", "length", "content_filter"
    "usage":               dict | None,      # {input_tokens, output_tokens, total_tokens, reasoning_tokens}
    "duration_ms":         float | None,
    "provider":            str,              # "anthropic", "openai", ...
    "model":               str,              # modelo resuelto del run
    "response_id":         str | None,       # ID del body del provider (del primer LLMCall)
    "response_model":      str | None,       # modelo que respondió (del primer LLMCall)
    "provider_timing":     dict | None,      # Cerebras / Groq specific
    "request_started_at":  str,              # = RunInfo.timestamp (ISO 8601 UTC, cuándo arrancó la call)
    "run_params":          dict,             # snapshot completo de kwargs efectivos del run
                                              # (ver nota sobre fix en core.py más abajo)
    "origin":              str,              # quién produjo la entry (loop_name si vino de un Loop, "manual"/etc si no)
    "run_id":              str,              # uuid de la invocación del orquestador (loop.run())
    "turn_num":            int,
}
```

**Notas sobre campos clave:**

- `text` mapea de `RunInfo.response_content`. **Siempre es un string** (verificado en `core.py:1040, 1048, 1202, 1236, 1241`). No contiene tool_calls ni reasoning — esos viven en sus propios campos.
- `reasoning` es campo separado al mismo nivel que `text` (no anidado). La view default lo incluye en el render. Importante para Anthropic extended thinking.
- `request_started_at` es el momento en que `agent.run` arrancó (antes de la llamada al provider). El `Entry.timestamp` (top-level del Entry, no en content) es el momento en que se escribió la entry al History — siempre **después** de la call. Diferencia ≈ `duration_ms`.
- `run_params` es el snapshot de kwargs efectivos. Ver nota sobre fix necesario en `core.py` en sección "Decisiones abiertas".

### Entry `tool_call`

```python
content = {
    "name":           str,                # te.name
    "arguments":      dict,                # te.arguments — YA parseado, intacto
    "result":         Any,                 # te.result — tipo nativo (dict, list, etc.)
    "exception":      str | None,          # te.exception (si la tool específica falló)
    "execution_mode": str,                 # "wait_response" / "execution_only" / "get_args"
    "origin":      str,
    "run_id":         str,
    "turn_num":       int,
}
```

**`razonamiento` no se extrae**. Es una convención de algunas tools del usuario, no universal. Si la tool aceptó `razonamiento` como argumento, queda en `arguments["razonamiento"]` como cualquier otro arg. Si la view markdown quiere mostrarlo distinto, esa lógica vive en la view, no en el bridge.

### Entry `error` (run-level)

Solo se emite si el run entero crasheó (`run_info.error` no es None). En ese caso no se emiten ni `response` ni `tool_call`s.

```python
content = {
    "exception":   str,
    "duration_ms": float | None,
    "provider":    str,
    "model":       str,
    "origin":   str,
    "run_id":      str,
    "turn_num":    int,
}
```

Distinto de `tool_call.content["exception"]` que captura una tool puntual fallida pero el run sobrevivió.

---

## Snapshot completo de `run_params` (reemplaza la lógica anterior de "overrides")

**Diseño actual**: el bridge guarda **el snapshot completo de kwargs efectivos** del run en `response.content.run_params`. No calcula diferencias contra defaults — guarda el set completo. Si necesitás el diff, lo computás al analizar logs comparando con `run_start.content.agent.defaults`.

```python
response_content["run_params"] = run_info.run_params or {}
```

**Por qué cambió**: la lógica anterior de calcular `overrides` tenía dos problemas:

1. **Filtrado por `k in default_run_params` dejaba afuera kwargs que no estaban en los defaults**. Por ejemplo, si pasás `agent.run(prompt, reasoning="high")` y el agente no tiene `reasoning` como default, la override se perdía.
2. **`RunInfo.run_params` actualmente captura solo 9 keys** (`core.py:658-668`): model, temperature, max_tokens, presence_penalty, frequency_penalty, stop, seed, execution_mode, stream. No incluye `reasoning`, `image_detail`, kwargs de `additional_params`, etc.

Guardar el snapshot completo es más simple y más correcto. El cost (algunos kwargs adicionales por entry) es despreciable comparado con la claridad.

**Pre-requisito**: hay un fix necesario en `core.py` para que `RunInfo.run_params` capture **todos** los kwargs efectivos, no solo 9. Ver sección "Decisiones abiertas" más abajo.

---

## Lo que NO va al History (por design)

| Campo de RunInfo | Por qué fuera |
|---|---|
| `messages_sent` literal | Pesado (MBs con imágenes en base64). No lo necesita el agente para continuar — la vista re-construye el contexto cada step. Si lo necesitás para audit/replay, se captura en el `RunLog` aparte (ver `log-design.md`). |
| `raw_response` (StandardResponse vivo) | No serializable directo, schema variable por provider. Queda accesible en memoria vía `agent.last_run.llm_calls[*].raw_response` mientras el agente exista. Tampoco va al RunLog. |
| `RunInfo.prompt` (el output de la vista que el Loop pasó a agent.run) | Reconstruible re-corriendo la vista. Pesa porque incluye history acumulado. Si querés bit-perfect, lo captura el `RunLog`. |
| `LLMCall[*].tool_calls_requested` (lo que el modelo PIDIÓ ejecutar) | En modo `wait_response` coincide con `tool_executions`. En modos no-wait diverge. Para el caso típico no aporta. Para análisis específico se captura en el RunLog. |
| `LLMCall[*]` detail per-call (multi-call dentro de un step) | El bridge agrega: solo response_id/response_model del primer call. Detalle per-call se captura en RunLog. |
| `api_key`, `service_account_file`, `location` | Sensibles, sanitizados, nunca se persisten. |
| `additional_params` libres del run | Inestables, opcionales, generalmente debugging. |
| `return_full_response`, `think_loud` | Afectan el shape del retorno o el streaming, no son data del run. |

---

## Debug pesado: opt-in del orquestador vía RunLog

El bridge **nunca** appendea data pesada al History. Si un orquestador necesita capturar `messages_sent` literal o detalle multi-call, lo hace via un **objeto separado**: `RunLog`. Ver `log-design.md`.

El History queda lean siempre. El RunLog vive en paralelo, opt-in vía `debug=True` en el Loop.

**Esto reemplaza la idea anterior de appendear entries `llm_debug` al History.** Lo pesado vive en su propio canal.

---

## Fix requerido en InstantNeo: `reasoning_tokens`

El bridge expone `usage["reasoning_tokens"]`, pero hoy `RunInfo.usage` no lo trae aunque el provider sí lo dé. Hay que arreglar dos lugares:

### `core.py` — propagar reasoning_tokens de `StandardUsage` al dict

En `_handle_normal_response` y `_handle_streaming_response` (~líneas 1219-1223 y 967-973):

```python
# Antes
llm_call.usage = {
    "input_tokens":  usage.input_tokens or 0,
    "output_tokens": usage.output_tokens or 0,
    "total_tokens":  usage.total_tokens or 0,
}

# Después
llm_call.usage = {
    "input_tokens":     usage.input_tokens or 0,
    "output_tokens":    usage.output_tokens or 0,
    "total_tokens":     usage.total_tokens or 0,
    "reasoning_tokens": getattr(usage, "reasoning_tokens", None),
}
run_info.usage = llm_call.usage
```

### Adapters — populizar `StandardUsage.reasoning_tokens`

| Adapter | Acción | Origen |
|---|---|---|
| `_chat_completions.py:244` | Ya lo hace ✓ | (Groq, xAI, Vertex Anthropic) |
| `openai_adapter.py:374` y stream | Agregar `reasoning_tokens=...` | `response.usage.completion_tokens_details.reasoning_tokens` o `output_tokens_details.reasoning_tokens` |
| `cerebras_adapter.py:275, 317, 342` | Agregar | `usage.completion_tokens_details.reasoning_tokens` si presente |
| `anthropic_adapter.py:355` | **No aplica** — Anthropic cuenta thinking tokens dentro de `output_tokens`, no separadamente. Documentar. | — |
| `gemini_adapter.py:385, 441` | Evaluar — Gemini 2.5+ expone `thoughts_token_count` en `usage_metadata` | Si está, agregarlo |

Después del fix, `agent.last_run.usage["reasoning_tokens"]` queda accesible (`None` si el provider no lo da).

---

## Issues relacionados (no bloquean el bridge)

- **`image_detail` ignorado en `process_images`**: bug pequeño en `instantneo/utils/image_utils.py:86-103`. Fix de 2 líneas (agregar `"detail": image_detail` al dict de imagen). Evaluar provider por provider qué soporta el campo. PR independiente.
- **Observabilidad de tokens granulares** (audio_tokens, cache breakdown): `StandardUsage` no tiene esos campos. Deuda técnica futura: extender `StandardUsage` y propagar desde fetchers que ya capturan. No bloquea nada.
- **Headers HTTP de la response** (rate limits, request id): ningún fetcher lee `response.headers`. Para observabilidad, el desideratum es que el fetcher los exponga en algún campo de StandardResponse. Deuda técnica futura.

---

## Tabla completa de equivalencias de naming

`RunInfo` upstream **no se modifica** (decisión explícita). El bridge mapea con consistencia documentada. Esta tabla es la referencia única — cualquier dev que vea una entry y se pregunte "de dónde viene esto" la consulta.

### Top-level de `RunInfo` → entries del History

| Campo de `RunInfo` | Entry destino | Campo en `content` | Notas |
|---|---|---|---|
| `provider` | `response`, `error` | `provider` | mismo nombre |
| `model` | `response`, `error` | `model` | mismo nombre |
| `prompt` | (no va al History) | — | va a `RunLog.turns[k].prompt` si `debug=True` |
| `execution_mode` | (no va al History) | — | se considera config, no per-run data |
| `stream` | (no va al History) | — | idem |
| `timestamp` | `response` | `request_started_at` | renombrado por claridad — `RunInfo.timestamp` upstream no cambia |
| `messages_sent` | (no va al History) | — | va a `RunLog.turns[k].messages_sent` si `debug=True` |
| `response_content` | `response` | `text` | renombrado por brevedad — siempre es string (verificado) |
| `finish_reason` | `response` | `finish_reason` | mismo nombre |
| `llm_calls[0].response_id` | `response` | `response_id` | solo del primer call (limitación documentada) |
| `llm_calls[0].response_model` | `response` | `response_model` | idem |
| `tool_executions` | `tool_call` (una por cada) | (ver tabla siguiente) | una entry por ToolExecution |
| `usage` | `response` | `usage` | mismo nombre (agregado de todos los calls) |
| `run_params` | `response` | `run_params` | snapshot completo (post-fix en core.py) |
| `error` | `error` | `exception` | renombrado por consistencia con `ToolExecution.exception` |
| `reasoning` | `response` | `reasoning` | mismo nombre |
| `duration_ms` | `response`, `error` | `duration_ms` | mismo nombre |
| `provider_timing` | `response` | `provider_timing` | mismo nombre |

### `ToolExecution` → entry `tool_call`

| Campo de `ToolExecution` | Campo en `content` | Notas |
|---|---|---|
| `name` | `name` | mismo nombre |
| `arguments` | `arguments` | mismo nombre — dict intacto, parseado |
| `result` | `result` | mismo nombre — tipo nativo, no `str()` |
| `exception` | `exception` | mismo nombre |
| `execution_mode` | `execution_mode` | mismo nombre |

### `LLMCall` (per-call) → no va al History en baseline

Si `debug=True`, va a `RunLog.turns[k].llm_calls`:

| Campo de `LLMCall` | Campo en `RunLog.turns[k].llm_calls[*]` |
|---|---|
| `messages_sent` | `messages_sent` |
| `response_content` | `response_content` |
| `finish_reason` | `finish_reason` |
| `tool_calls_requested` | `tool_calls_requested` |
| `usage` | `usage` |
| `response_id` | `response_id` |
| `response_model` | `response_model` |
| `reasoning_content` | `reasoning_content` |
| `raw_response` | (excluido — no serializable) |

### Reglas de naming aplicadas

1. **Mantener el mismo nombre que el origen**, salvo razón fuerte (claridad o consistencia).
2. **Renames documentados**: cuando un nombre cambia, queda registrado acá con la razón.
3. **`RunInfo` y los modelos upstream no se tocan** — el bridge es donde vive la traducción.
4. **Excepciones explícitas**:
   - `response_content` → `text`: brevedad (`text` se lee más natural en `response.content.text`).
   - `timestamp` → `request_started_at`: claridad (`Entry.timestamp` ya existe como concepto distinto).
   - `RunInfo.error` → `error.content.exception`: alineación con `ToolExecution.exception`.

---

## Verificación (cuando se implemente)

Tests del bridge, todos puros sobre `RunInfo` sintéticos:

- `test_append_entry_from_run_response_only` — RunInfo con response, sin tools.
- `test_append_entry_from_run_with_tools` — response + N tool_executions.
- `test_append_entry_from_run_only_tools` — sin response_content (e.g. execution_only).
- `test_append_entry_from_run_with_run_error` — solo entry error, no más.
- `test_append_entry_from_run_with_tool_exception` — tool falló, run sobrevivió.
- `test_append_entry_from_run_preserves_arguments_dict` — arguments queda como dict, no string.
- `test_append_entry_from_run_preserves_result_native` — result queda nativo, no str().
- `test_append_entry_from_run_includes_reasoning` — reasoning entra al content como campo separado.
- `test_append_entry_from_run_includes_reasoning_tokens` — usage incluye reasoning_tokens cuando el RunInfo lo tiene.
- `test_append_entry_from_run_with_overrides` — params per-turn que difieren de defaults se registran como `overrides`.
- `test_append_entry_from_run_includes_origin_and_run_id` — toda entry generada lleva esos dos campos en su content.
- `test_append_from_run_method_delegates_to_function` — `history.append_from_run(...)` y `append_entry_from_run(history, ...)` producen el mismo resultado.
- `test_append_entry_from_run_returns_appended_entries` — el return value es la lista appendeada en orden.

Tests adicionales relacionados al fix de `reasoning_tokens` en InstantNeo viven en sus propios archivos por adapter.

---

## Layout

```
instantneo/
  history/
    from_run_info.py    # función append_entry_from_run
    queries.py          # current_run_config(history) y otros helpers
```

---

## Decisiones abiertas

### Fix necesario en `core.py`: `RunInfo.run_params` debe capturar TODOS los kwargs

Hoy `RunInfo.run_params` se construye en `core.py:658-668` capturando solo 9 keys hardcodeadas:

```python
run_params={
    "model":             run_params.model,
    "temperature":       run_params.temperature,
    "max_tokens":        run_params.max_tokens,
    "presence_penalty":  run_params.presence_penalty,
    "frequency_penalty": run_params.frequency_penalty,
    "stop":              run_params.stop,
    "seed":              run_params.seed,
    "execution_mode":    run_params.execution_mode,
    "stream":            run_params.stream,
}
```

**Problemas con esto:**

1. **No captura `reasoning`, `image_detail`, `tools=` per-run, `additional_params`, ni cualquier otra kwarg**. Si pasás `agent.run(prompt, reasoning="high")`, `reasoning` no queda en `run_params`.
2. **El bridge depende de este snapshot** para `response.content.run_params`. Si está incompleto, el snapshot está incompleto.
3. **Lo mismo aplica al RunLog** — `TurnLog.run_params` lee de aquí.

**Fix**: extender la construcción de `RunInfo.run_params` en `core.py` para capturar **todos los kwargs efectivos** del run. Idealmente, mediante un método tipo `RunParams.to_dict()` que devuelva todo. PR independiente, prerequisito tanto para el bridge (snapshot correcto) como para el RunLog.

**Mientras tanto**: el bridge guarda lo que haya. El snapshot queda parcial pero funcional para los 9 kwargs principales.

---

## Pendiente

- **Loop**: documentado por separado en `loop-design.md`. Es quien llama `append_entry_from_run` y emite las entries operacionales (`run_start`, `step_start`, `step_end`, `error` operacional, `stop_signal`, `run_end`).
- **RunLog**: documentado por separado en `log-design.md`. Es la pieza opt-in vía `debug=True` que captura todo lo que el bridge descarta del `RunInfo` (prompt rendered, messages_sent, multi-call detail).
- **PR de fix de `reasoning_tokens`** en InstantNeo: independiente, antes o en paralelo con el bridge.
- **PR de fix de `RunInfo.run_params`** en core.py: descrito arriba.
- **Migración del `instant_loop.py` actual** al nuevo Loop: doc separado cuando sea momento.
