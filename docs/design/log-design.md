# Log — diseño y API

Documento del **RunLog**: registro estructurado y completo de un `loop.run()`, paralelo al History. Vive como objeto separado, opt-in vía `debug=True` en el Loop. Captura todo lo que pasó (incluyendo `prompt_sent`, `messages_sent`, detalle per-LLM-call) sin contaminar el History con data pesada que el agente no necesita.

También se documenta acá el caso de uso de **InstantNeo solo**, sin Loop, mediante un helper más simple.

---

## Idea central

El **History** es el log operacional del agente: lo que necesita la vista para construir el prompt del próximo turno + lo mínimo para observabilidad casual (text, reasoning, tool calls, usage, errors).

El **RunLog** es el log forense del orquestador: todo lo anterior **plus** lo que se descarta del `RunInfo` (prompt rendered, messages literal, detalle multi-call). Más metadata fija (config completa del agente, schemas de tools, role_setup resolved) repetida por conveniencia de auto-suficiencia.

**Coexisten en paralelo, no se contaminan:**

```
                    ┌────────────────┐
                    │  History       │  ← log operacional, append-only
                    │  (lean)         │     baseline ligero
                    └────────┬───────┘
                             ▲
                             │ Loop appendea entries
                             │
                  ┌──────────┴────────────┐
                  │   loop.run()           │
                  └──────────┬────────────┘
                             │
            si debug=True    │ además
                             ▼
                    ┌────────────────┐
                    │  RunLog         │  ← log forense, por-run
                    │  (rich)         │     completo y separado
                    └────────┬───────┘
                             │
                             ▼ se escribe turn-by-turn a disco
                    ┌────────────────┐
                    │  folder.json    │
                    └────────────────┘
```

**Reglas que sostienen el diseño:**

- El **History no cambia con `debug=True`**. Tiene su baseline siempre — agregar debug NO le mete entries `llm_debug` ni nada parecido. El History sigue siendo el log operacional, agente-focused.
- El **RunLog es un objeto separado**. Vive solo cuando `debug=True`. Tiene su propia clase, su propio ciclo de vida.
- Cada step del Loop, **además** de appendear las entries operacionales al History, popula el `RunLog` con un `TurnLog` y lo escribe a disco apenas termina (resiliencia ante crashes).
- Hay **compatibilidad bidireccional History ↔ RunLog** vía helpers — para replay, reconstrucción, importación de runs anteriores.
- El **caso InstantNeo solo** (sin Loop) usa los mismos primitivos compartidos pero con una agregación más simple. Helper específico: `write_agent_call_log`.
- **Los primitivos son reutilizables por cualquier orquestador futuro** (Pipeline, etc.) sin tocar InstantNeo ni reimplementar serialización.

---

## Arquitectura en capas — primitivos compartidos

El sistema de logging está pensado en **tres capas** para que distintos consumidores (Loop solo, InstantNeo solo, Pipeline futuro, etc.) compartan los mismos building blocks. **InstantNeo no se modifica** en ningún caso — los helpers leen `agent.config` y `agent.last_run` desde afuera.

### Capa 1 — Primitivos genéricos (no acoplados a Loop)

Viven en `instantneo/debug.py` (módulo top-level, no dentro de `loop/`).

**Dataclass: `TurnLog`** — representa una llamada de `agent.run()`. Mismo shape para todos los contextos (Loop step, solo call, Pipeline stage agent invocation).

**Funciones:**

- `build_agent_config(agent: InstantNeo) -> dict` — extrae la cabecera completa del agente (provider, model, role_setup, role_setup_resolved, tools schemas, defaults), **sanitizada** (sin `api_key`, `service_account_file`, `location`).
- `extract_tool_schemas(agent: InstantNeo) -> list[dict]` — produce la lista `[{name, description, parameters}, ...]` desde `agent.capabilities`.
- `TurnLog.from_runinfo(...)` — método de la dataclass que convierte un `RunInfo` (de `agent.last_run`) en `TurnLog`.
- `write_json(path: Path, data: dict) -> None` — utilidad de escritura JSON-safe (con `default=str` para tipos no estándar dentro de `content`).
- `sanitize_secrets(config: dict) -> dict` — filtra keys sensibles (`api_key`, `service_account_file`, `location`).

Estos primitivos **no saben nada de orquestadores**. Solo manejan datos de InstantNeo crudos.

### Capa 2 — Agregaciones por orquestador

Cada orquestador define su propio "log container" que **compone los primitivos**.

**Para `InstantLoop`** (hoy): `RunLog` con `turns: list[TurnLog]`, en `instantneo/loop/debug.py`.

**Para `InstantNeo` solo** (sin orquestador): no hay aggregator class — el helper `write_agent_call_log` usa los primitivos directamente para escribir un folder con `config.json` + `call.json`.

**Para `Pipeline` futuro**: tendrá su propia `PipelineLog` con su shape (probablemente `stages: list[StageLog]` donde cada StageLog tiene su lista de `TurnLog`s). Reutilizará los primitivos.

### Capa 3 — Helpers de usuario final

Funciones de conveniencia para los casos típicos:

- `write_agent_call_log(agent, path, ...)` — para uso de InstantNeo solo.
- `load_run_logs(loop_folder)` — para cargar múltiples runs de un Loop.
- `load_agent_call_logs(folder)` — para cargar múltiples calls solo (paralela al anterior).

### Mapa visual

```
┌────────────────────────────────────────────────────────────────┐
│ Capa 3 — Helpers de usuario final                              │
│   write_agent_call_log()      load_run_logs()                  │
│   load_agent_call_logs()      (futuros)                        │
└──────────────────┬─────────────────────────────────────────────┘
                   │ usan
                   ▼
┌────────────────────────────────────────────────────────────────┐
│ Capa 2 — Agregaciones por orquestador                          │
│   RunLog (Loop)         PipelineLog (futuro)                   │
│   instantneo/loop/      instantneo/pipeline/                   │
│   debug.py              debug.py                               │
└──────────────────┬─────────────────────────────────────────────┘
                   │ componen
                   ▼
┌────────────────────────────────────────────────────────────────┐
│ Capa 1 — Primitivos genéricos                                  │
│   TurnLog                build_agent_config()                  │
│   extract_tool_schemas() sanitize_secrets()                    │
│   write_json()           (otros utilitarios)                   │
│   instantneo/debug.py                                          │
└──────────────────┬─────────────────────────────────────────────┘
                   │ leen
                   ▼
┌────────────────────────────────────────────────────────────────┐
│ InstantNeo (intacto, sin modificar)                            │
│   agent.config        agent.capabilities                       │
│   agent.last_run (RunInfo)                                     │
└────────────────────────────────────────────────────────────────┘
```

**Cualquier orquestador nuevo solo necesita escribir su Capa 2**. Las Capas 1 y 3 se reusan o extienden mínimamente.

---

## Estructura — `RunLog` y `TurnLog`

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class TurnLog:
    """Todo lo que pasó en un step de un loop.run()."""
    # Identificación
    step_num:            int
    started_at:          str                              # ISO 8601 UTC, cuándo arrancó el step
    completed_at:        Optional[str]                    # ISO, None si crasheó

    # Lo que el Loop le mandó al agente
    prompt:              str                              # = RunInfo.prompt (output de la vista)
    images:              Optional[list[dict]]             # refs/paths/URLs, no base64
    image_detail:        Optional[str]

    # Lo que InstantNeo armó para el provider
    messages_sent:       list[dict]                       # = RunInfo.messages_sent (formato provider)
    run_params:          dict                             # snapshot completo de kwargs efectivos del run

    # Lo que el LLM produjo (consolidado al cierre)
    response_content:    Optional[str]                    # texto final, = RunInfo.response_content
    reasoning:           Optional[str]                    # extended thinking, = RunInfo.reasoning
    finish_reason:       Optional[str]                    # = RunInfo.finish_reason
    usage:               Optional[dict]                   # tokens agregados

    # Detalle per-LLM-call (puede ser más de una por step)
    llm_calls:           list[dict]                       # cada call: messages_sent, response_id, etc.

    # Ejecución de herramientas en este step
    tool_executions:     list[dict]                       # name, arguments, result, exception, execution_mode

    # Timing del provider
    provider:            str
    model:               str
    response_id:         Optional[str]                    # del primer call
    response_model:      Optional[str]
    duration_ms:         Optional[float]                  # tiempo del agent.run completo
    provider_timing:     Optional[dict]                   # Cerebras / Groq specific
    request_started_at:  str                              # = RunInfo.timestamp (ISO, cuándo arrancó la call)

    # Si hubo error
    error:               Optional[str]                    # = RunInfo.error

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "TurnLog": ...
    @classmethod
    def from_runinfo(
        cls,
        *,
        step_num: int,
        started_at: str,
        completed_at: Optional[str],
        run_info: "RunInfo",
    ) -> "TurnLog": ...


@dataclass
class RunLog:
    """Log completo de UN loop.run()."""
    # Identificación
    log_id:              str                              # uuid único del Log mismo
    run_id:              str                              # matchea con History run_start.run_id
    loop_name:           str                              # matchea con History run_start.origin
    sequence_num:        int                              # 1, 2, 3... posición dentro de la vida del Loop

    # Cronología
    started_at:          str                              # ISO, cuándo arrancó loop.run()
    completed_at:        Optional[str]                    # ISO, cuándo cerró loop.run()
    terminated_reason:   Optional[str]                    # "stop_signal" | "view" | "external" | "max_steps" | "error"
    stop_reason:         Optional[str]                    # string específico que disparó el stop

    # Cabecera fija — todo lo necesario para reproducibilidad
    config:              dict = field(default_factory=dict)   # ver shape abajo

    # Cronología detallada
    turns:               list[TurnLog] = field(default_factory=list)

    # Folder donde se está escribiendo (si aplica)
    output_path:         Optional[Path] = None

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "RunLog": ...

    def append_turn(self, turn: TurnLog) -> None:
        """Agrega un turn y, si output_path está set, escribe turn_NNN.json a disco."""

    def write_config(self) -> None:
        """Escribe config.json al output_path. Se llama al inicio del run."""

    def write_run_end(self) -> None:
        """Escribe run_end.json al output_path. Se llama al cierre del run."""

    def write_full(self, path: Optional[Path] = None) -> None:
        """Escribe TODO el log a disco en una sola pasada (config + turns + run_end)."""

    @classmethod
    def load_folder(cls, path: Path) -> "RunLog":
        """Carga un RunLog desde un folder previamente escrito."""

    def to_history_entries(self) -> list[dict]:
        """Convierte el RunLog en la secuencia de entries que iría al History."""

    @classmethod
    def from_history(cls, history: "History", run_id: str) -> "RunLog":
        """Reconstruye un RunLog desde un History dado.

        Nota: si el run no se corrió con debug=True, los campos
        prompt/messages_sent/llm_calls quedan None/[].
        """
```

### Shape de `RunLog.config`

```python
config = {
    "agent": {
        "name":                 str,
        "provider":             str,
        "model":                str,
        "role_setup":           str,                       # original
        "role_setup_resolved":  str,                       # con tool_instructions + shelf_context inyectados
        "tools": [                                          # schemas completos, no solo nombres
            {
                "name":        str,
                "description": str,
                "parameters":  dict,                       # JSON Schema del tool
            },
            ...
        ],
        "defaults": {                                       # de InstantNeoParams, sin secrets
            "temperature":       float | None,
            "max_tokens":        int | None,
            "presence_penalty":  float | None,
            "frequency_penalty": float | None,
            "stop":              str | list | None,
            "seed":              int | None,
            "stream":            bool,
            "image_detail":      str | None,
            # ... y cualquier otro kwarg que tenga default
        },
        # NO incluye api_key, service_account_file, location
    },
    "loop": {
        "name":          str,
        "max_steps":     int,                              # 0 = sin cap
        "view":          str,
        "stop_signals":  list[str],
        "stop_tool":     list[str] | None,                 # resuelto a lista (o None si no se usó)
        "monitor_rules": list[str],                        # nombres de rules registradas
        "debug":         bool,                              # siempre True acá (porque hay log)
    },
    "input": {
        "prompt":       str,                                # el prompt del user a loop.run()
        "images":       list[dict] | None,                 # refs/paths/URLs
        "image_detail": str | None,
    },
}
```

---

## Folder structure y nombres

Cuando `debug=True`, el Loop crea un folder y escribe ahí. La estructura está pensada para **ordenamiento cronológico natural** + **agrupación por loop** + **identificación única por run**.

```
debug_output/                                                    ← base configurable por el dev
└── <loop_name>/                                                  ← un folder por Loop
    ├── 20260509_143215_run_001_a3f7c2/                            ← un folder por run
    │   ├── config.json
    │   ├── turn_001.json
    │   ├── turn_002.json
    │   ├── ...
    │   └── run_end.json
    │
    ├── 20260509_143752_run_002_b8e1d5/
    │   └── ...
    │
    └── 20260509_150301_run_003_c4f9a1/
        └── ...
```

### Nomenclatura

```
<YYYYMMDD_HHMMSS>_run_<seq_num_zero_padded>_<run_id_short>/
```

- **`YYYYMMDD_HHMMSS`**: timestamp UTC del inicio del run. **Ordenable lexicográficamente** — un `ls` ya te da cronología.
- **`run_<seq_num>`**: ordinal dentro del loop (1, 2, 3...). Zero-padded a 3 dígitos (`001`, `002`) para ordenamiento natural hasta 999 runs por loop.
- **`<run_id_short>`**: primeros 6 caracteres del `run_id` (uuid). Suficiente unicidad para que dos runs nunca colisionen aun si arrancaran en el mismo segundo.

**Ejemplo concreto:**

```
debug_output/investigador/20260509_143215_run_001_a3f7c2/
debug_output/investigador/20260509_143752_run_002_b8e1d5/
debug_output/critico/20260509_143230_run_001_d2a8f4/
```

Con esto, **ordenar por timestamp da el orden real de ejecución entre todos los loops**:

```bash
find debug_output/ -mindepth 2 -maxdepth 2 -type d | sort
# 20260509_143215_run_001_a3f7c2  (investigador)
# 20260509_143230_run_001_d2a8f4  (critico)
# 20260509_143752_run_002_b8e1d5  (investigador)
```

### Archivos dentro del folder de un run

| Archivo | Cuándo se escribe | Contenido |
|---|---|---|
| `config.json` | al inicio (post `run_start`) | RunLog.config |
| `turn_001.json` | apenas termina el step 1 | TurnLog.to_dict() del step 1 |
| `turn_002.json` | apenas termina el step 2 | idem |
| `turn_NNN.json` | idem | idem |
| `run_end.json` | al cierre de loop.run() (success o error) | metadata final: terminated_reason, stop_reason, completed_at, duration_s, total_steps |

**Resiliencia ante crash**: si el proceso muere a mitad del step 3, en disco quedan `config.json`, `turn_001.json`, `turn_002.json` (completos). Sin `run_end.json`, sabés que no terminó.

---

## Ciclo de vida

Secuencia exacta de lo que pasa cuando `debug=True`:

```
loop.__init__():
    self.debug = True
    self._run_counter = 0           # contador de runs de este Loop
    self._debug_base_path = ...     # base del folder donde escribir
                                     # default: Path("debug_output/") configurable
                                     # más adelante via env var o param

loop.run(prompt, ...):
    self._run_counter += 1
    run_id = uuid4().hex
    started_at = datetime.utcnow().isoformat()
    
    # 1. Crear el RunLog
    log = RunLog.new(
        run_id=run_id,
        loop_name=self.name,
        sequence_num=self._run_counter,
        started_at=started_at,
        config={                     # construir desde self.agent y self
            "agent": self._build_agent_config(),
            "loop":  self._build_loop_config(),
            "input": {"prompt": prompt, "images": images, "image_detail": image_detail},
        },
    )
    
    # 2. Preparar folder y escribir config.json
    log.output_path = self._compute_run_folder(started_at, run_id)
    log.output_path.mkdir(parents=True, exist_ok=True)
    log.write_config()
    
    # 3. Per-step
    for step_num in 1..N:
        step_started_at = datetime.utcnow().isoformat()
        
        # (A) Render del prompt vía vista
        # (B) agent.run(...)
        # (C) Bridge appendea al History
        # (D) Monitor
        # (E) step_end appendeado al History
        # (F) Crear TurnLog y appendear al RunLog
        
        step_completed_at = datetime.utcnow().isoformat()
        turn = TurnLog.from_runinfo(
            step_num=step_num,
            started_at=step_started_at,
            completed_at=step_completed_at,
            run_info=self.agent.last_run,
        )
        log.append_turn(turn)
        # append_turn escribe turn_NNN.json a disco internamente

    # 4. Cierre
    log.completed_at = datetime.utcnow().isoformat()
    log.terminated_reason = terminated_reason
    log.stop_reason = stop_reason
    log.write_run_end()

    return RunResult(..., log=log)
```

**Sin debug=True (caso default), el código del Loop ni siquiera entra a estas ramas** — el flag es chequeado al inicio y simplemente no crea el log.

---

## API completa

### `RunLog` — métodos públicos

#### Constructor

```python
@classmethod
def new(
    cls,
    *,
    run_id: str,
    loop_name: str,
    sequence_num: int,
    started_at: str,
    config: dict,
) -> "RunLog":
    """Crea un RunLog nuevo, sin turns, sin output_path asignado."""
```

#### Mutación durante la ejecución

```python
def append_turn(self, turn: TurnLog) -> None:
    """Agrega el TurnLog a self.turns.

    Si self.output_path está set, también escribe turn_NNN.json a disco
    (donde NNN es turn.step_num zero-padded a 3 dígitos).
    """

def write_config(self) -> None:
    """Escribe self.config + metadata (log_id, run_id, loop_name, sequence_num, started_at)
    al archivo config.json en self.output_path.

    Raises ValueError si output_path no está set.
    """

def write_run_end(self) -> None:
    """Escribe metadata final (completed_at, terminated_reason, stop_reason, total_steps,
    duration_s) al archivo run_end.json en self.output_path.

    Idempotente: se puede llamar varias veces; sobrescribe.
    """
```

#### Serialización

```python
def to_dict(self) -> dict:
    """Convierte el RunLog completo a dict serializable JSON."""

@classmethod
def from_dict(cls, data: dict) -> "RunLog":
    """Reconstruye un RunLog desde un dict (e.g., leído de JSON)."""

def write_full(self, path: Optional[Path] = None) -> None:
    """Escribe TODO el log a disco en una sola pasada — config.json + turn_NNN.json
    por cada turn + run_end.json — al path dado (o self.output_path si está set).

    Útil para serializar al final sin haber escrito incrementalmente.
    """

@classmethod
def load_folder(cls, path: Path) -> "RunLog":
    """Carga un RunLog desde un folder previamente escrito."""
```

#### Compatibilidad con History

```python
def to_history_entries(self) -> list[dict]:
    """Convierte el RunLog en la secuencia de entries (dicts) que reflejan el run.

    El return value es serializable. Cada dict tiene shape:
        {"author": str, "type": str, "content": dict, "refs": tuple}

    Para appendear al History:
        for entry_dict in log.to_history_entries():
            history.append(**entry_dict)
    """

@classmethod
def from_history(cls, history: "History", run_id: str) -> "RunLog":
    """Reconstruye un RunLog desde un History.

    Limitación: el History NO contiene los campos pesados de debug (prompt rendered,
    messages_sent, multi-call detail). Esa data, si el run original se corrió con
    debug=True, vive en el RunLog del momento (no en el History).

    Por lo tanto, un RunLog reconstruido desde History tendrá los campos
    operacionales (text, reasoning, tool_executions, usage, etc.) pero los campos
    pesados (prompt, messages_sent, llm_calls detail) quedarán como None/[].

    Útil para análisis post-hoc cuando solo se conserva el History.
    """
```

### `TurnLog` — métodos públicos

```python
def to_dict(self) -> dict:
    """Serializa a dict JSON-safe."""

@classmethod
def from_dict(cls, data: dict) -> "TurnLog":
    """Deserializa desde dict."""

@classmethod
def from_runinfo(
    cls,
    *,
    step_num: int,
    started_at: str,
    completed_at: Optional[str],
    run_info: "RunInfo",
) -> "TurnLog":
    """Construye un TurnLog a partir de un RunInfo de InstantNeo.

    Mapea todos los campos relevantes. No incluye raw_response (no serializable).
    """
```

### Reglas de naming dentro del Log

| Campo del Log | Equivalente en `RunInfo` / `LLMCall` / `ToolExecution` |
|---|---|
| `TurnLog.prompt` | `RunInfo.prompt` (el output de la vista que el Loop pasó a agent.run) |
| `TurnLog.messages_sent` | `RunInfo.messages_sent` (formato provider) |
| `TurnLog.response_content` | `RunInfo.response_content` |
| `TurnLog.reasoning` | `RunInfo.reasoning` |
| `TurnLog.finish_reason` | `RunInfo.finish_reason` |
| `TurnLog.usage` | `RunInfo.usage` |
| `TurnLog.provider` | `RunInfo.provider` |
| `TurnLog.model` | `RunInfo.model` |
| `TurnLog.duration_ms` | `RunInfo.duration_ms` |
| `TurnLog.provider_timing` | `RunInfo.provider_timing` |
| `TurnLog.request_started_at` | `RunInfo.timestamp` (renombrado por claridad — RunInfo NO se cambia) |
| `TurnLog.error` | `RunInfo.error` |
| `TurnLog.llm_calls` | `RunInfo.llm_calls` (lista de LLMCall serializados, sin `raw_response`) |
| `TurnLog.tool_executions` | `RunInfo.tool_executions` (lista de ToolExecution serializados) |
| `TurnLog.response_id`, `response_model` | `LLMCall.response_id`, `response_model` (del **primer** call) |
| `TurnLog.run_params` | `RunInfo.run_params` (snapshot completo de kwargs efectivos) |

**Regla**: usar el mismo nombre que el origen salvo donde la claridad sea fuerte (caso `request_started_at` ← `timestamp`). El `RunInfo` upstream **no se modifica**.

---

## Helpers — distribuidos según capa

Recordando la arquitectura en capas, los helpers se distribuyen así:

### En `instantneo/debug.py` (Capa 1 — genéricos)

#### `build_agent_config(agent: InstantNeo) -> dict`

Extrae la cabecera completa del agente, sanitizada. Output:

```python
{
    "name":                 str,
    "provider":             str,
    "model":                str,
    "role_setup":           str,
    "role_setup_resolved":  str,
    "tools":                list[ToolSchema],
    "defaults":             dict,
}
```

Es la sección `"agent"` que aparece tanto en `RunLog.config` como en `config.json` de uso solo.

#### `extract_tool_schemas(agent: InstantNeo) -> list[dict]`

Produce la lista `[{name, description, parameters}, ...]` desde `agent.capabilities`. Si el agente tiene 0 tools, retorna `[]`.

#### `sanitize_secrets(d: dict) -> dict`

Devuelve una copia del dict sin las keys sensibles (`api_key`, `service_account_file`, `location`). Si la key está pero su valor es None, se la deja (no es secreto).

#### `write_json(path: Path, data: dict) -> None`

Utility para escribir JSON con `indent=2`, `ensure_ascii=False`, `default=str` para serializar tipos no estándar.

#### `TurnLog` dataclass y métodos

Ver sección "Estructura" más arriba. Vive en este módulo porque es genérico (no específico de Loop).

#### `write_agent_call_log(agent, path, *, call_id=None, started_at=None, extra=None) -> Path`

Ya documentado arriba en "Uso sin Loop". Vive aquí.

#### `load_agent_call_logs(folder: Path) -> list[dict]`

Ya documentado arriba.

### En `instantneo/loop/debug.py` (Capa 2 — agregación del Loop)

#### `RunLog` dataclass y sus métodos

Ver secciones "Estructura" y "API completa". Específico de Loop.

#### `load_run_logs(loop_folder: Path) -> list[RunLog]`

```python
def load_run_logs(loop_folder: Path) -> list[RunLog]:
    """Carga todos los RunLogs presentes en el folder de un loop.

    Ordena por sequence_num ascendente. Los runs incompletos (sin run_end.json)
    se cargan igual con completed_at=None.

    Útil para reconstruir la cronología de runs consecutivos de un loop.
    """
```

Uso:

```python
from instantneo.loop.debug import load_run_logs

logs = load_run_logs(Path("debug_output/investigador/"))
for log in logs:
    print(f"Run {log.sequence_num}: {log.config['input']['prompt']}")
    print(f"  → terminó por {log.terminated_reason}: {log.stop_reason}")
    print(f"  → {len(log.turns)} steps en {log.completed_at}")
```

#### `_new_run_log_for_loop(loop, run_id, started_at_iso, prompt, images, image_detail) -> RunLog`

Helper privado usado por el Loop al construir el `RunLog` al inicio del run. Compone `build_agent_config(loop.agent)` con la config del Loop.

---

## Compatibilidad para futuros orquestadores

El sistema está pensado para que **cualquier orquestador nuevo** (Pipeline, Coordinator, etc.) reutilice los primitivos sin reimplementar serialización ni manejo de folder.

### Hipotético: `Pipeline` con stages

Imaginemos un `Pipeline` que ejecuta varios agentes en sequence/parallel, cada uno con sus tools. Cada stage del Pipeline invoca `agent.run()` una o más veces.

Diseño esperable de su Log:

```python
# instantneo/pipeline/debug.py

from instantneo.debug import TurnLog, build_agent_config


@dataclass
class StageLog:
    """Log de una stage del Pipeline."""
    stage_name:    str
    agent_calls:   list[TurnLog]       # ← reusa el primitivo
    started_at:    str
    completed_at:  str | None


@dataclass
class PipelineLog:
    """Log de una ejecución de Pipeline."""
    log_id:           str
    run_id:           str               # mismo concepto que en RunLog
    pipeline_name:    str
    sequence_num:     int               # ordinal dentro de la vida del Pipeline
    started_at:       str
    completed_at:     str | None
    terminated_reason: str | None

    config: {
        "pipeline": {
            "name":    str,
            "stages":  list[str],       # nombres de stages
        },
        "agents":      list[dict],       # un dict por agente involucrado, usando build_agent_config
        "input":       dict,
    }

    stages:           list[StageLog]
    output_path:      Path | None

    def to_dict(self) -> dict: ...
    def write_config(self) -> None: ...
    # ... métodos equivalentes a RunLog ...
```

Folder structure paralela:

```
debug_output/
└── <pipeline_name>/
    └── <YYYYMMDD_HHMMSS>_run_<seq>_<run_id>/
        ├── config.json
        ├── stage_001_<stage_name>/
        │   ├── call_001.json
        │   ├── call_002.json
        │   └── ...
        ├── stage_002_<stage_name>/
        │   └── ...
        └── run_end.json
```

**Lo importante**: cada `call_NNN.json` dentro de una stage es **el mismo shape que un `turn_NNN.json` del Loop o un `call.json` solo**. Mismo `TurnLog.to_dict()` produciéndolo. Los analizadores funcionan igual.

### Cómo Pipeline reusaría primitivos

Concretamente:

1. **Cabecera de cada agente**: `build_agent_config(agent)` en `instantneo.debug`. Se llama por cada agente que el Pipeline use.
2. **Cada call**: `TurnLog.from_runinfo(run_info)` en `instantneo.debug`. Idéntico al Loop.
3. **Escritura JSON**: `write_json(path, data)` en `instantneo.debug`.
4. **Sanitización**: `sanitize_secrets(dict)` en `instantneo.debug`.

El Pipeline **solo escribe su Capa 2** (PipelineLog, StageLog, su writer). Las Capas 1 y 3 (donde aplique) se reusan.

### Beneficios del diseño en capas

| Beneficio | Cómo se materializa |
|---|---|
| **InstantNeo nunca se modifica** | Los helpers leen de `agent.config`, `agent.capabilities`, `agent.last_run` desde afuera. |
| **Un solo lugar de serialización** | `TurnLog.to_dict()` es la única implementación. Si cambia el shape, cambia en un lugar. |
| **Compatibilidad entre orquestadores** | El JSON de un call de Loop, Solo o Pipeline tiene **el mismo shape**. Tools de análisis funcionan transversalmente. |
| **Nuevos orquestadores con poca fricción** | Para implementar un nuevo orquestador, escribís su Capa 2 (~150-300 líneas) y reusás todo lo demás. |
| **Sin acoplamiento circular** | InstantNeo no depende de `instantneo/debug.py`. `instantneo/debug.py` depende de InstantNeo (lee de él). El Loop usa ambos. Topología limpia. |

---

## Layout final de archivos

```
instantneo/
├── debug.py                          ← Capa 1 (genérica) + helpers para solo
│   ├── TurnLog (dataclass + métodos)
│   ├── build_agent_config()
│   ├── extract_tool_schemas()
│   ├── sanitize_secrets()
│   ├── write_json()
│   ├── write_agent_call_log()
│   └── load_agent_call_logs()
│
├── loop/
│   ├── instant_loop.py               ← InstantLoop
│   ├── default_view.py               ← loop_default + RenderedPrompt
│   └── debug.py                      ← Capa 2 del Loop
│       ├── RunLog (dataclass + métodos)
│       ├── load_run_logs()
│       └── _new_run_log_for_loop()  (privado)
│
├── pipeline/                         ← (futuro)
│   ├── pipeline.py
│   └── debug.py                      ← Capa 2 del Pipeline (PipelineLog, StageLog)
│
└── ... (resto del paquete)
```

### Re-exports convenientes

Para que el usuario no tenga que recordar paths exactos:

```python
# instantneo/__init__.py exporta:
from instantneo.debug import (
    TurnLog,
    write_agent_call_log,
    load_agent_call_logs,
)
from instantneo.loop.debug import (
    RunLog,
    load_run_logs,
)
```

Así se usa:

```python
from instantneo import (
    InstantNeo, InstantLoop,
    History, Monitor,
    RunLog, TurnLog,
    write_agent_call_log, load_run_logs, load_agent_call_logs,
)
```

Todo en un namespace plano para uso frecuente.

---

## Uso sin Loop — `write_agent_call_log` en detalle

Cuando trabajás solo con `InstantNeo` (sin `InstantLoop`), no hay concepto de "run" multi-step ni de "loop con history". Cada `agent.run(prompt)` es una unidad atómica. El helper para ese caso es **liviano y compatible** con el sistema de logging del Loop: usa los mismos primitivos (`TurnLog`, `build_agent_config`, etc.) y produce folders con shape conocido.

### Folder structure para uso solo

```
debug_output/
└── <namespace_o_agent_name>/                                ← namespace que vos elijas (default: agent.name o "manual")
    ├── 20260509_143215_call_001_a3f7c2/
    │   ├── config.json                                       ← cabecera del agente (mismo shape que en Loop)
    │   └── call.json                                          ← TurnLog completo de esta call
    │
    ├── 20260509_143752_call_002_b8e1d5/
    │   ├── config.json
    │   └── call.json
    │
    └── 20260509_143830_call_003_c4f9a1/
        ├── config.json
        └── call.json
```

Comparación con la del Loop:

| Aspecto | Loop | Solo InstantNeo |
|---|---|---|
| Folder raíz por contexto | `<loop_name>/` | `<namespace>/` (default `<agent.name>/` o `"manual/"`) |
| Folder por evento | `<ts>_run_<seq>_<id>/` | `<ts>_call_<seq>_<id>/` |
| Archivos por evento | `config.json` + `turn_NNN.json` × N + `run_end.json` | `config.json` + `call.json` |
| Tipo de "unidad" | un run con N turns | un solo call |
| Sequence number | incrementa por `.run()` de un Loop | incrementa por `.write_agent_call_log()` (manejado por el caller) |

La nomenclatura `<ts>_call_<seq>_<id>/` es **paralela** a `<ts>_run_<seq>_<id>/` para que ambos casos sean fácilmente browseables juntos en el mismo `debug_output/`.

### Shape de los archivos

#### `config.json` (mismo shape que el del Loop, sección `"agent"`)

```python
{
    "agent": {
        "name":                 str,                            # agent.name o "agent"
        "provider":             str,
        "model":                str,
        "role_setup":           str,                            # system prompt original
        "role_setup_resolved":  str,                            # con tool_instructions + shelf_context inyectados
        "tools": [                                               # schemas completos
            {"name": str, "description": str, "parameters": dict},
            ...
        ],
        "defaults":             dict,                            # de InstantNeoParams, sin secrets
    },
    "captured_at":             str,                            # ISO UTC, cuándo se escribió
    "call_id":                 str,                            # uuid de esta call (matches con sub-folder name)
    "extra":                   dict | None,                     # metadata custom opcional del caller
}
```

Notar: **la sección `"agent"` es idéntica** a la que aparece en `RunLog.config["agent"]` del Loop. Esto permite que helpers de análisis compartan código entre ambos casos.

#### `call.json` (un `TurnLog` serializado)

```python
# Todo lo que TurnLog.to_dict() devuelve.
# Es el mismo shape que cada turn_NNN.json del Loop:
{
    "step_num":            1,                                  # solo hay 1 call por folder, así que siempre 1
    "started_at":          str,
    "completed_at":        str,
    "prompt":              str,                                # = RunInfo.prompt
    "images":              list[dict] | None,
    "image_detail":        str | None,
    "messages_sent":       list[dict],
    "run_params":          dict,
    "response_content":    str | None,
    "reasoning":           str | None,
    "finish_reason":       str | None,
    "usage":               dict | None,
    "llm_calls":           list[dict],
    "tool_executions":     list[dict],
    "provider":            str,
    "model":               str,
    "response_id":         str | None,
    "response_model":      str | None,
    "duration_ms":         float | None,
    "provider_timing":     dict | None,
    "request_started_at":  str,
    "error":               str | None,
}
```

Mismo shape que un `turn_NNN.json` del Loop. La compatibilidad es bit-perfect a nivel de estructura.

### Firma del helper `write_agent_call_log`

```python
def write_agent_call_log(
    agent: InstantNeo,
    path: Path | str,
    *,
    call_id: str | None = None,
    started_at: str | None = None,
    extra: dict | None = None,
) -> Path:
    """Persiste el último agent.run() a un folder.

    Para uso de InstantNeo sin orquestador. Equivale a un único TurnLog
    serializado en su folder, paralelo a la estructura del Loop.

    Args:
        agent: La instance de InstantNeo. Debe tener `agent.last_run` poblado
            (es decir, debe haberse llamado agent.run() antes).
        path: Folder donde escribir. Si no existe, se crea (parents=True).
            Se escriben dos archivos: config.json y call.json.
        call_id: UUID opcional para este call. Si no se pasa, se autogenera.
        started_at: Timestamp ISO UTC del momento en que arrancó la call.
            Si no se pasa, se usa el de agent.last_run.timestamp.
        extra: dict opcional con metadata custom para meter en config.json bajo
            la key "extra".

    Returns:
        El path del folder escrito (mismo que el arg `path`, resuelto a Path).

    Raises:
        RuntimeError: si agent.last_run es None (no se llamó agent.run() antes).
        OSError: si no se puede escribir al filesystem.
    """
```

### Ejemplos de uso

#### Caso simple — un call

```python
from pathlib import Path
from instantneo.debug import write_agent_call_log
from instantneo import InstantNeo

agent = InstantNeo(...)
agent.run("describí esta imagen", images=["foto.jpg"])

write_agent_call_log(
    agent,
    Path("debug_output/manual/20260509_143215_call_001_a3f7c2/"),
)
# Escribe config.json + call.json en ese folder.
```

#### Caso típico — colección de calls con cronología

Si hacés varias calls y querés todos los folders prolijos, el caller maneja el counter y el timestamp:

```python
import datetime, uuid
from pathlib import Path
from instantneo.debug import write_agent_call_log

agent = InstantNeo(name="investigador", ...)
base = Path("debug_output/investigador/")
counter = 0

for prompt in mi_lista_de_prompts:
    counter += 1
    agent.run(prompt)

    ts       = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    call_id  = uuid.uuid4().hex
    folder   = base / f"{ts}_call_{counter:03d}_{call_id[:6]}/"

    write_agent_call_log(agent, folder, call_id=call_id)
```

#### Helper opcional para usar el namespace automático

Si querés que el helper maneje el folder por vos (timestamp + counter automático), usá la variante de más alto nivel:

```python
from instantneo.debug import write_agent_call_log_auto

agent = InstantNeo(name="investigador", ...)

# Mantiene un counter interno asociado al `(base_path, agent.name)` en memoria del proceso
for prompt in mi_lista_de_prompts:
    agent.run(prompt)
    write_agent_call_log_auto(
        agent,
        base_path=Path("debug_output/"),
    )
# Crea automáticamente: debug_output/investigador/<ts>_call_<seq>_<id>/...
```

Esta variante es trivial de implementar (mantiene un dict `{(base, name): counter}` en memoria del módulo). No es esencial pero acorta el caso típico.

### Carga inversa — `load_agent_call_logs`

Para cargar todas las calls solo de un agent:

```python
def load_agent_call_logs(folder: Path) -> list[dict]:
    """Carga todos los call folders presentes en el folder dado.

    Devuelve una lista ordenada por timestamp (lexicográfico del prefijo
    YYYYMMDD_HHMMSS). Cada elemento es:
        {
            "folder":    Path,             # el folder de este call
            "config":    dict,             # contenido de config.json
            "call":      dict,             # contenido de call.json (TurnLog dict)
        }
    """
```

Uso:

```python
from instantneo.debug import load_agent_call_logs

logs = load_agent_call_logs(Path("debug_output/investigador/"))
# Ordenados cronológicamente
for log in logs:
    print(f"{log['config']['captured_at']}: prompt={log['call']['prompt'][:80]!r}")
    print(f"  → response: {log['call']['response_content'][:80] if log['call']['response_content'] else 'None'}")
```

Paralela a `load_run_logs` que carga RunLogs del Loop. Las dos retornan estructuras navegables.

### Por qué hay un agregador (RunLog) para Loop pero no para solo

Diseño minimalista:

- **Loop**: cada `.run()` genera N turns, hay una sequence_num, hay un terminated_reason. Tiene sentido un objeto agregador `RunLog` con sus métodos (`write_full`, `to_history_entries`, etc.).
- **Solo**: cada `agent.run()` es una unidad atómica. No hay multiplicidad, no hay sequence_num naturalmente (lo maneja el caller). Un objeto agregador sería ceremonia innecesaria.

Si necesitás algo más rico — por ejemplo, "sesión sin Loop" que junta varios calls con metadata propia — escribís tu propio wrapper. Pero esto está fuera de scope; la librería provee primitivos.

---

## Compatibilidad bidireccional con History

### `RunLog → History entries`

```python
log = RunLog.load_folder(Path("debug_output/investigador/20260509_143215_run_001_a3f7c2/"))

new_history = History()
for entry_dict in log.to_history_entries():
    new_history.append(**entry_dict)

# Ahora new_history tiene un run completo replicado:
new_history.by_type("response")        # responses del run
new_history.by_type("tool_call")        # tool calls del run
new_history.export("loop_default")      # renderea como lo vería un agente
```

Esto te permite **replicar un run de un Log antiguo a un History fresco**. Útil para:

- Cargar logs históricos en una sesión actual.
- Hacer "fork" desde un punto de un log anterior (cargás N entries y seguís con un nuevo Loop).
- Reproducir un escenario para depuración.

### `History → RunLog`

```python
log = RunLog.from_history(history, run_id="a3f7c2...")
log.write_full(path=Path("debug_output/replay/"))
```

Reconstruye desde el History. Limitación: si el run original no se corrió con `debug=True`, los campos `prompt`, `messages_sent`, `llm_calls` quedan vacíos (porque esa data nunca estuvo en el History — solo en el `RunLog` original que ya no tenemos).

Para que `from_history` sea fiel, el run debe haber tenido `debug=True` en su momento.

---

## Reconstrucción de runs consecutivos del mismo Loop

Caso de uso: tenés una conversación larga con un Loop, varias invocaciones `.run()` sobre el mismo History. Querés ver la cronología completa.

```python
from instantneo.loop.debug import load_run_logs
from pathlib import Path

logs = load_run_logs(Path("debug_output/investigador/"))
# logs ordenados por sequence_num: [run_1, run_2, run_3, ...]

# Cada log es un RunLog independiente. Comparten loop_name.
# El run_id es distinto por run.

# Para análisis cronológico:
for log in logs:
    print(f"Run {log.sequence_num} ({log.run_id[:8]}) @ {log.started_at}")
    print(f"  Input: {log.config['input']['prompt']}")
    print(f"  Outcome: {log.terminated_reason} → {log.stop_reason}")
    print(f"  Steps: {len(log.turns)}")
    for turn in log.turns:
        if turn.tool_executions:
            tools = [te['name'] for te in turn.tool_executions]
            print(f"    Step {turn.step_num}: tools {tools}")
```

**Para reconstruir el History resultante de la cadena entera** (caso: se perdió el History, querés rearmarlo):

```python
history = History()

for log in logs:
    for entry_dict in log.to_history_entries():
        history.append(**entry_dict)

# Ahora history tiene la cadena completa de runs, con todos los run_ids preservados.
```

---

## Lo que el Log NO captura — explícito

| Campo / dato | ¿En el Log? | Por qué no |
|---|---|---|
| `LLMCall.raw_response` (StandardResponse vivo) | **No** | No serializable de forma confiable; schema variable por provider |
| Imágenes en base64 | **No directamente** | `TurnLog.images` guarda refs/paths/URLs, no bytes. `TurnLog.messages_sent` puede contener base64 si InstantNeo lo procesó así (dependiente del provider) — eso queda como vino |
| `api_key`, `service_account_file`, `location` (secrets) | **No** | Sanitizado al armar config |
| El estado interno del agente entre runs | N/A | InstantNeo no tiene estado entre `agent.run()` calls; cada call es fresh |
| Logs externos (Datadog, Sentry, etc.) | **No** | Fuera de scope; los Monitor actions out-of-band los emiten en paralelo |

---

## Tests (cuando se implemente)

### Tests de Capa 1 (`instantneo/debug.py`)

Tests de `TurnLog`:

- `test_turnlog_from_runinfo_maps_all_fields_correctly`
- `test_turnlog_from_runinfo_excludes_raw_response`
- `test_turnlog_to_dict_roundtrip`
- `test_turnlog_from_dict_reconstructs_correctly`

Tests de `build_agent_config`:

- `test_build_agent_config_includes_all_required_keys`
- `test_build_agent_config_extracts_tool_schemas_with_parameters`
- `test_build_agent_config_resolves_role_setup_with_tool_instructions`
- `test_build_agent_config_resolves_role_setup_with_shelf_context`
- `test_build_agent_config_no_tools_returns_empty_list`

Tests de `sanitize_secrets`:

- `test_sanitize_secrets_removes_api_key`
- `test_sanitize_secrets_removes_service_account_file`
- `test_sanitize_secrets_preserves_non_sensitive_keys`
- `test_sanitize_secrets_handles_nested_dicts`

Tests de `extract_tool_schemas`:

- `test_extract_tool_schemas_returns_list_of_dicts`
- `test_extract_tool_schemas_each_has_name_description_parameters`
- `test_extract_tool_schemas_empty_when_no_tools`

Tests de `write_agent_call_log` (uso solo):

- `test_write_agent_call_log_creates_folder_with_config_and_call`
- `test_write_agent_call_log_config_matches_build_agent_config_output`
- `test_write_agent_call_log_call_matches_turnlog_dict_shape`
- `test_write_agent_call_log_raises_if_last_run_is_none`
- `test_write_agent_call_log_with_call_id_uses_it_in_config`
- `test_write_agent_call_log_with_extra_includes_it_in_config`

Tests de `load_agent_call_logs`:

- `test_load_agent_call_logs_returns_sorted_list`
- `test_load_agent_call_logs_includes_folder_path`
- `test_load_agent_call_logs_skips_invalid_folders`

### Tests de Capa 2 — `RunLog` (`instantneo/loop/debug.py`)

Tests del `RunLog`:

- `test_runlog_new_creates_empty_log_with_metadata`
- `test_runlog_append_turn_adds_to_turns_list`
- `test_runlog_append_turn_with_output_path_writes_file`
- `test_runlog_write_config_serializes_correctly`
- `test_runlog_write_run_end_serializes_correctly`
- `test_runlog_to_dict_roundtrip`
- `test_runlog_write_full_writes_all_files`
- `test_runlog_load_folder_reconstructs_correctly`
- `test_runlog_load_folder_handles_missing_run_end`

Tests de compatibilidad con History:

- `test_to_history_entries_produces_valid_entry_dicts`
- `test_to_history_entries_replicates_run_when_appended_to_fresh_history`
- `test_from_history_reconstructs_log_without_debug_fields`
- `test_from_history_leaves_heavy_fields_empty` — confirma que prompt/messages_sent/llm_calls quedan None/[]

Tests de `load_run_logs`:

- `test_load_run_logs_orders_by_sequence_num`
- `test_load_run_logs_includes_incomplete_runs`

### Tests de integración con Loop

- `test_loop_with_debug_true_creates_runlog_and_returns_in_result`
- `test_loop_with_debug_false_returns_result_log_none`
- `test_loop_with_debug_writes_folder_with_correct_naming`
- `test_loop_with_debug_writes_turn_files_incrementally`
- `test_loop_crash_mid_step_leaves_partial_folder_usable`

### Tests de compatibilidad de shape entre Loop y Solo

- `test_loop_turn_json_and_solo_call_json_have_same_shape` — clave para la compatibilidad
- `test_loop_config_agent_section_matches_solo_config_agent_section` — la sección `"agent"` debe ser idéntica

---

## Implementación / decisiones abiertas

### Path base del folder

¿Dónde se escribe por default? Opciones:

- **Constructor del Loop**: `InstantLoop(..., debug=True, debug_path=Path("debug_output/"))` — explícito.
- **Variable de entorno**: `INSTANTNEO_DEBUG_PATH=...` — implícito, sirve sin tocar código.
- **Cwd**: `Path.cwd() / "debug_output"` — default razonable.
- **Combinación**: param explícito gana, sino env var, sino cwd.

Recomendación: la combinación. Param explícito en el constructor para casos controlados; env var para deploys; cwd como último fallback.

### Sequence num — contador del Loop

El `RunLog.sequence_num` lo lleva el Loop como `self._run_counter`, incrementado al inicio de cada `.run()`. Persiste mientras la instancia del Loop existe.

**Limitación**: si destruís y recreás el Loop, el counter arranca en 1 de nuevo. Si querés continuidad entre instancias, deberías persistir el counter (en disco, por ejemplo en `debug_output/<loop_name>/.counter`). Por ahora, no.

Esto está alineado con el principio de que el Loop **vive en memoria**; persistir el counter sería trabajo extra que rara vez se necesita.

### Concurrencia (escritura desde múltiples threads)

Si una action del Monitor escribe entries al History desde un thread separado mientras el Loop está armando el `TurnLog`, hay potencial race condition. **Solución actual**: no soportar concurrencia en v1. El History tampoco la soporta (sin locking en `append`). Cuando se aborde, será conjunto.

### Si crasea durante `append_turn`

Si `append_turn(turn)` falla escribiendo `turn_NNN.json` (disco lleno, permisos, etc.):

- Opción A: re-raise — el Loop crashea, pero el caller sabe que algo anda mal.
- Opción B: log a stderr y continuar — más resiliente, menos visible.

Recomendación: **A**. Si no podés escribir el log, querés saberlo. La data en memoria está y se devuelve en `RunResult.log` igual.

### Cuándo cerrar handles a archivos

Cada escritura abre y cierra el archivo (Pathlib `write_text`). No mantenemos handles abiertos entre steps. Simple, no requiere cleanup.

---

## Pendiente / migración

### Pre-requisitos en código existente (independientes del Log)

1. **Fix de `core.py` — `RunInfo.run_params`**: actualmente captura solo 9 keys (model, temperature, max_tokens, presence_penalty, frequency_penalty, stop, seed, execution_mode, stream) en `core.py:658-668`. Para que `TurnLog.run_params` sea snapshot completo, hay que extender la construcción para incluir TODOS los kwargs efectivos del run (incluyendo `reasoning`, `image_detail`, `tools=`, etc.). Sin esto, el snapshot queda parcial pero funcional. **PR aparte.**

2. **Exponer tool schemas en InstantNeo**: necesitamos `agent.capabilities.get_schemas()` (o similar) que devuelva `[{name, description, parameters}, ...]`. Hoy existe parcial como `formatted_tools` en `core.py`. Hay que exponerlo público y limpio. **PR aparte.**

3. **Exponer `role_setup_resolved` en InstantNeo**: la lógica de `_prepare_messages` arma el system prompt final (con `tool_instructions` + `shelf_context` inyectados). Hay que exponer como método público (e.g. `agent.get_resolved_role_setup() -> str`). **PR aparte.**

### Pasos de implementación (orden recomendado)

1. **PRs pre-requisitos** (1, 2, 3 de arriba): independientes, pueden ir en paralelo. No bloquean el resto si el snapshot queda parcial al inicio.

2. **PR de Capa 1 — `instantneo/debug.py`**:
   - Dataclass `TurnLog` con `from_runinfo`, `to_dict`, `from_dict`.
   - Funciones `build_agent_config`, `extract_tool_schemas`, `sanitize_secrets`, `write_json`.
   - Helper `write_agent_call_log`.
   - Helper `load_agent_call_logs`.
   - Tests por componente.

3. **PR de Capa 2 — `instantneo/loop/debug.py`**:
   - Dataclass `RunLog` con todos sus métodos (`new`, `append_turn`, `write_config`, `write_run_end`, `write_full`, `load_folder`, `to_history_entries`, `from_history`).
   - Helper `load_run_logs`.
   - Helper privado `_new_run_log_for_loop`.
   - Tests por componente.

4. **PR de integración con `InstantLoop`**:
   - 3-5 líneas en `__init__` (init counter, base_path).
   - 3-5 líneas en `run` (crear log al inicio, append_turn por step, write_run_end al cierre).
   - Campo `log: RunLog | None` en `RunResult`.
   - Tests de integración.

5. **PR de re-exports en `instantneo/__init__.py`**: para uso ergonómico de `from instantneo import TurnLog, RunLog, write_agent_call_log, load_run_logs, load_agent_call_logs`.

Los pasos 2 y 3 pueden ir como un solo PR si conviene — son lógicamente separados pero pequeños. El paso 4 depende de 3.

### Decisiones abiertas adicionales

- **Schema versioning**: incluir `"schema_version": 1` en `config.json`, `turn_NNN.json` (y `call.json`), `run_end.json` desde el inicio. Permite evolución futura sin romper loaders. Implementación trivial:

  ```python
  SCHEMA_VERSION = 1
  def write_versioned(path, data):
      write_json(path, {"schema_version": SCHEMA_VERSION, **data})
  ```

  Los loaders chequean y warneean si encuentran versión distinta.

- **Compresión del folder cuando un loop_name acumula muchos runs**: cuando un loop_name tiene 1000+ subfolders, leer todos los configs cuesta. Si surge la necesidad, agregamos `index.json` en el folder del loop con resumen de runs (sequence_num, run_id, started_at, terminated_reason). No bloquea v1.

- **Streaming de actualizaciones live**: el `progress.json` del legacy era live para herramientas externas. Hoy no lo cubrimos por default — un dev que necesite progress live lo arma con una rule del Monitor que escriba a un archivo cada step (`persist_progress(path)`). Documentar como recipe.

- **Counter no persistente entre instancias del Loop**: el `sequence_num` lo lleva el Loop como `self._run_counter`. Si destruís y recreás el Loop, arranca en 1 de nuevo. Para continuidad real entre instancias habría que persistir el counter (e.g. `<base>/<loop_name>/.counter`). Si surge la necesidad, lo agregamos.

- **Concurrencia** (escritura desde múltiples threads): no se soporta en v1, igual que el History. Cuando se aborde, se hace en conjunto.

- **Format alternativo a JSON** (msgpack, parquet, etc.): no en v1. JSON cubre el caso típico, es human-readable, y permite parsing con cualquier herramienta.

- **Mocking de `agent.last_run` para tests**: los tests construyen `RunInfo` sintéticos (precedente: tests del bridge). Convención: helpers en `tests/fixtures/run_info.py`.

- **Imports y namespace**: ver "Layout final" más arriba.
