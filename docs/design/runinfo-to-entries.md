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
) -> list[Entry]:
    """Descompone un RunInfo en entries y las appendea al History.

    Genera, en orden:
      - 1 entry type='error' si run_info.error (y retorna).
      - 1 entry type='response' si run_info.response_content.
      - N entries type='tool_call', una por cada tool_execution.

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
    "text":            str,             # run_info.response_content
    "reasoning":       str | None,       # run_info.reasoning (thinking del modelo)
    "finish_reason":   str,              # "stop", "tool_calls", "length", "content_filter"
    "usage":           dict | None,      # {input_tokens, output_tokens, total_tokens, reasoning_tokens}
    "duration_ms":     float | None,
    "provider":        str,              # "anthropic", "openai", ...
    "model":           str,              # modelo resuelto del run
    "response_id":     str | None,       # ID del body del provider
    "response_model":  str | None,       # modelo que respondió (puede diferir del solicitado)
    "provider_timing": dict | None,      # Cerebras / Groq specific
    "turn_num":        int,
}
```

`reasoning` es campo separado al mismo nivel que `text` (no anidado). La view que alimenta al agente puede o no incluirlo en el render — la convención default propuesta es **incluirlo**, especialmente importante para Anthropic extended thinking donde el provider espera ver los thinking blocks de turnos previos para mantener continuidad.

### Entry `tool_call`

```python
content = {
    "name":           str,                # te.name
    "arguments":      dict,                # te.arguments — YA parseado, intacto
    "result":         Any,                 # te.result — tipo nativo (dict, list, etc.)
    "exception":      str | None,          # te.exception (si la tool específica falló)
    "execution_mode": str,                 # "wait_response" / "execution_only" / "get_args"
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
    "turn_num":    int,
}
```

Distinto de `tool_call.content["exception"]` que captura una tool puntual fallida pero el run sobrevivió.

---

## Per-turn config overrides

Cuando el caller hace `agent.run(prompt, temperature=0.9, ...)`, esos overrides están en `run_info.run_params`. Si **difieren** de los defaults registrados en `run_start.content["agent"]["defaults"]`, el bridge los agrega como `overrides` en el response content:

```python
default_run_params = current_run_config(history)["agent"]["defaults"]
this_run_params = run_info.run_params or {}

overrides = {
    k: v for k, v in this_run_params.items()
    if k in default_run_params and default_run_params[k] != v
}

if overrides:
    response_content["overrides"] = overrides
```

Cuando no hay overrides (caso típico), `response.content` no carga ese campo. Mantiene per-turn entries livianas pero registra cambios cuando ocurren.

---

## Lo que NO va al History (por design)

| Campo de RunInfo | Por qué fuera |
|---|---|
| `messages_sent` literal | Redundante con appendear cada turno; multiplicado por base64 de imágenes y la conversación acumulada → O(n²) por run. Si el History se persiste, la conversación se reconstruye desde sus entries. |
| `raw_response` (StandardResponse vivo) | No serializable directo, schema variable por provider. Queda accesible en memoria vía `agent.last_run.llm_calls[*].raw_response` mientras el agente exista. |
| `llm_calls[*].tool_calls_requested` | Redundante con `tool_call` entries; `tool_executions` ya tiene los args parseados y el result. |
| `api_key`, `service_account_file` | Sensibles, nunca se persisten. |
| `additional_params` libres del run | Inestables, opcionales, generalmente debugging. |
| `return_full_response`, `think_loud` | Afectan el shape del retorno o el streaming, no son data del run. |

---

## Debug pesado: opt-in del orquestador

El bridge no incluye debug pesado. Si un orquestador necesita capturar `messages_sent` literal para reproducción/análisis profundo, lo hace **él mismo** appendendo una entry adicional del tipo `llm_debug`:

```python
# Decisión del orquestador (no del bridge), si self.debug:
if self.debug:
    history.append(
        author="orchestrator",
        type="llm_debug",
        content={
            "messages_sent": agent.last_run.messages_sent,
            "turn_num":      step_num,
        },
    )
```

Eso vive en el código del Loop (cuando lleguemos al doc del Loop), nunca en el bridge.

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

## Pendiente

- **Loop**: documentado por separado en `loop-design.md`. Es quien llama `append_entry_from_run` y emite las entries operacionales (`run_start`, `step_start`, `step_end`, `error` operacional, `stop_signal`, `run_end`).
- **PR de fix de `reasoning_tokens`** en InstantNeo: independiente, antes o en paralelo con el bridge.
- **Migración del `instant_loop.py` actual** al nuevo Loop: doc separado cuando sea momento.
