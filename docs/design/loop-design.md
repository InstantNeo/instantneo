# Loop — diseño y API

Documento del **InstantLoop**, el orquestador concreto que corre un agente InstantNeo en un loop multi-step usando History + Monitor + bridge `append_entry_from_run`. Reemplaza el `instant_loop.py` actual con un diseño que aprovecha la arquitectura event-sourced.

---

## Idea central

El Loop ejecuta un agente InstantNeo en `N` steps consecutivos. Cada step:

1. Materializa la vista del History para construir el prompt del agente.
2. Invoca `agent.run(prompt, ...)`.
3. Descompone el `RunInfo` resultante en entries vía el bridge.
4. Emite las entries operacionales del step (`step_start`, `step_end`).
5. Invoca `self.monitor(self.history)` para que las reglas registradas reaccionen.
6. Chequea `stop_signal` para decidir si seguir.

Termina cuando: alguna acción del Monitor appendea un `stop_signal`, se agota `max_steps`, o el agente crashea de forma irrecuperable.

**Reglas del diseño:**

- El Loop **es el dueño** de las entries operacionales (`run_start`, `step_start`, `step_end`, `error`, `run_end`). El bridge no las emite.
- El Loop **no muta** el History de otra forma que no sea `history.append(...)`.
- El Loop **tiene su propio Monitor** (paridad con `agent.capabilities` en InstantNeo). Lo construye desde el param `monitors=` con el mismo patrón que InstantNeo usa para `tools=`.
- El Loop **registra** una vista default `loop_default` al construirse, que el agente consume si no se especifica otra.
- Cada entry escrita durante un `loop.run()` (operacional o vía bridge) lleva `origin` (= `self.name`) y `run_id` en su `content`. La convención `origin` es genérica para cualquier orquestador (Loop, Pipeline futuro, script manual).

---

## API de `InstantLoop`

```python
from typing import Optional
from instantneo import InstantNeo
from instantneo.history import History
from instantneo.monitor import Monitor


class InstantLoop:
    def __init__(
        self,
        *,
        agent: InstantNeo,
        history: Optional[History] = None,
        name: Optional[str] = None,
        monitors: Optional[Monitor | list[Monitor]] = None,
        view: str = "loop_default",
        max_steps: int = 30,
        stop_signals: Optional[list[str]] = None,
        stop_tool: Optional[str | list[str]] = None,
        debug: bool = False,
    ):
        ...

    def run(
        self,
        prompt: str,
        *,
        images: Optional[str | list[str]] = None,
        image_detail: Optional[str] = None,
    ) -> RunResult:
        ...

    def stop(self, reason: str = "external") -> None:
        """Cancela el run en curso. Pone un flag interno; el Loop rompe al final
        del step actual con terminated_reason='external' y stop_reason=reason."""
        ...
```

### Parámetros del constructor

| Param | Tipo | Default | Rol |
|---|---|---|---|
| `agent` | `InstantNeo` | requerido | El agente que el Loop ejecuta en cada step |
| `history` | `History \| None` | `None` (crea uno) | El History al que se appendea. Si es None, el Loop instancia uno propio. Si se pasa uno existente, el Loop lo reutiliza (multi-run sobre el mismo History) |
| `name` | `str \| None` | autogenerado (uuid corto) | Identificador del Loop. Se estampa en cada entry como `content["origin"]`. Útil en escenarios multi-loop sobre un mismo History para filtrar el log |
| `monitors` | `Monitor \| list[Monitor] \| None` | `None` (Monitor vacío) | Mismo patrón que `InstantNeo(tools=...)`. Una instance → asignación directa. Lista → `MonitorOperations.union`. None → `Monitor()` vacío. El Loop invoca su monitor una vez por step, post-bridge |
| `view` | `str` | `"loop_default"` | Nombre de la vista que el agente consume para construir su prompt cada turno |
| `max_steps` | `int` | `30` | Límite duro de steps. **Si pasás `0`, el Loop NO tiene turnos máximos** — corre hasta que un `stop_signal` (Monitor) o un error lo detenga. Convención tomada de `queue.Queue(maxsize=0)`, `socket.listen(0)`, etc. Cualquier `int >= 1` es un cap real. Cualquier valor negativo o no-int → error al construir |
| `stop_signals` | `list[str] \| None` | `None` | Lista de strings que el Loop "escucha". Cuando aparece una entry de `type="stop_signal"` cuyo `content["text"]` está en esta lista, el Loop rompe con esa razón. Ver sección "Stop conditions" para el detalle |
| `stop_tool` | `str \| list[str] \| None` | `None` | Sugar para el caso típico: "cuando el agente llama tal tool, parar". Auto-configura whitelist + rule del Monitor. Ver sección "Stop conditions" |
| `debug` | `bool` | `False` | Si True, el Loop construye y persiste un `RunLog` separado del History con todo lo necesario para replay y audit (`prompt_sent`, `messages_sent`, detalle per-LLM-call, etc.). El History NO cambia con esta flag — sigue siendo lean. Ver `log-design.md` para el detalle del RunLog y la estructura del folder en disco |

> ### `max_steps=0` significa SIN cap
>
> Es decisión consciente y explícita. Cuando pasás `max_steps=0`:
>
> - El Loop **no tiene turnos máximos**. No hay límite numérico.
> - Solo termina por: `stop_signal` (rule del Monitor) o `error` no recuperable.
> - **Tu responsabilidad** configurar al menos una rule de stop, usar `stop_tool`, o llamar `loop.stop()` desde afuera.
> - Sin condiciones de stop, el Loop corre indefinidamente. La librería no valida esto al construir — confía en el dev.
>
> Si te incomoda escribir `max_steps=0` y querés algo más legible, hacelo vos a nivel de tu código: `MAX_STEPS_NONE = 0` o similar. La librería no provee constante con nombre porque mantiene el principio de "menos símbolos públicos".

> **Sobre las imágenes**: la responsabilidad de qué imágenes el agente ve en cada turno la tiene la **Vista**, no el Loop. La default `loop_default` las pasa en cada turno (matching legacy). Si querés otro comportamiento, registrás una vista custom o usás el parámetro `image_policy` de la default. Ver sección "Vista `loop_default`" más abajo.

### Parámetros de `loop.run()`

Compatible con la firma de `InstantNeo.run()` para los kwargs relevantes:

| Param | Tipo | Default | Rol |
|---|---|---|---|
| `prompt` | `str` | requerido | Instrucción inicial del run |
| `images` | `str \| list[str] \| None` | `None` | Imágenes que viajan con el prompt. Se pasan a `agent.run()` y quedan registradas en la entry `prompt` inicial |
| `image_detail` | `str \| None` | `None` | Idem `image_detail` de InstantNeo |

**Imágenes — comportamiento por default**: la **Vista** decide qué imágenes el agente ve en cada turno. La default `loop_default` las pasa en cada turno (matching legacy). La entry `prompt` guarda solo refs (paths/URLs/ids), no base64. Si querés optimizar tokens o tenés un caso multimodal complejo, registrás una vista custom o usás el parámetro `image_policy` de la default. Ver sección "Vista `loop_default`".

### `RunResult`

```python
from instantneo.loop.debug import RunLog   # forward reference

@dataclass
class RunResult:
    history:           History
    name:              str              # name del Loop (estable entre runs)
    run_id:            str              # uuid de esta invocación
    terminated_reason: str              # "stop_signal" | "view" | "external" | "max_steps" | "error"
    stop_reason:       str | None       # string específico que causó el stop, None si max_steps
    duration_s:        float
    total_steps:       int              # cuántos steps efectivamente corrieron
    log:               RunLog | None    # populado si se construyó con debug=True, None si no
```

Distinción importante:

- **`terminated_reason`** = la **categoría** por la cual paró. Útil para ramificar lógica programática (`if result.terminated_reason == "max_steps": ...`).
- **`stop_reason`** = el **string específico** del signal que disparó. Útil para entender qué pasó concretamente (`"mencionó Pepito"`, `"error fatal"`, `"timeout externo"`). `None` cuando paró por `max_steps` (no hay un texto asociado).
- **`log`** = el `RunLog` estructurado con todo lo del run (incluyendo `prompt_sent`, `messages_sent`, etc.). Solo populado si `debug=True` al construir el Loop. Si fue `False`, este campo es `None`.

Acceso al detalle del run:

- Para vista operacional (lo que el agente ve, métricas, queries): `result.history.all()`, `result.history.export(view_name)`, `result.history.by_type(...)`.
- Para debug forense / replay (con `debug=True`): `result.log.turns`, `result.log.config`, `result.log.write_full(path)`. Detalle en `log-design.md`.

El `RunResult` en sí es solo metadata + dos punteros (History y Log opcional). Los datos pesados viven en los dos contenedores.

---

## El parámetro `history` — comportamiento detallado

`history` recibe **una instancia ya construida** de `History`. No acepta strings, paths, ni clases.

### Casos del default

| Si pasás | Pasa |
|---|---|
| `history=mi_history` | El Loop usa esa instancia. La guarda en `self.history`. Appendea ahí durante cada `.run()` |
| `history=None` (o no pasás el kwarg) | El Loop crea una con `History()` y la guarda. Accesible vía `loop.history` después |

### Reglas de propiedad y reuso

**(1) El Loop NO es dueño del History — solo escribe en él.**

Si pasás un History existente, sigue siendo tuyo. Lo seguís refiriendo desde tu código. El Loop lo comparte, no se lo apropia. Esto permite multi-loop sobre la misma instancia:

```python
history = History()
loop_A = InstantLoop(agent=A, history=history, name="investigador")
loop_B = InstantLoop(agent=B, history=history, name="critico")

loop_A.run("...")      # appendea entries con origin="investigador"
loop_B.run("...")      # appendea entries con origin="critico"

# El history es uno solo, con entries de ambos Loops mezcladas en orden temporal.
print(history.all())
```

**(2) Puede tener contenido previo.**

El Loop **no exige un History vacío**. Puede recibir uno con entries de runs anteriores, sesiones cargadas de disco, o appendeadas manualmente:

```python
# Cargar un history previo de disco
import json
data = json.load(open("session_001.json"))
history = History.from_dicts(data)

# Continuar trabajando sobre él
loop = InstantLoop(agent=A, history=history)
loop.run("seguí donde dejaste")
# El run_start de este nuevo run lleva run_id nuevo;
# las entries previas conservan sus run_ids antiguos.
```

Decidir si la **vista** del agente le muestra entries de runs anteriores o solo del run actual es **decisión de la vista, no del History ni del Loop**. La default `loop_default` toma una postura concreta (ver sección de Vista). El usuario puede registrar otra que decida distinto.

**(3) Sin History pasado, el Loop crea uno aislado.**

```python
loop = InstantLoop(agent=A)            # history=None implícito
loop.run("...")
result = loop.history.all()             # accesible después
```

Caso típico para uso simple: scripts one-shot, evaluaciones independientes, pruebas.

### Resolución de la vista al construir

Al construirse, el Loop verifica que `view` (el parámetro, default `"loop_default"`) sea utilizable contra el History pasado. Algoritmo:

```python
def _ensure_view_available(self):
    if self.history.has_view(self.view):
        # El user (u otro Loop sobre el mismo History) ya la registró.
        # Usar la suya, sin tocarla.
        return

    if self.view == "loop_default":
        # Caso default: registrar la built-in del Loop.
        self.history.add_view("loop_default", _build_loop_default_view())
    else:
        # El user pidió una vista custom y no la registró.
        # Fallar temprano, no en pleno run.
        raise LoopConfigError(
            f"Vista '{self.view}' no registrada en el History. "
            f"Registrala antes de construir el Loop, o usá la default 'loop_default'."
        )
```

Cuatro escenarios cubiertos:

**(a) Default puro — el Loop registra `loop_default` solo:**

```python
history = History()
loop = InstantLoop(agent=A, history=history)
# view="loop_default" no existía → Loop la registró con la built-in
loop.run("...")
```

**(b) User override de `loop_default`:**

```python
history = History()

@history.view("loop_default")
def my_default(history):
    ...   # versión custom

loop = InstantLoop(agent=A, history=history)
# loop_default ya existía (la del user) → Loop usa la del user, no la built-in
```

**(c) User pasa una vista distinta y la registra él:**

```python
history = History()

@history.view("solo_notas")
def solo_notas(history):
    notas = history.by_type("note")
    return "\n\n".join(n.content["text"] for n in notas)

loop = InstantLoop(agent=A, history=history, view="solo_notas")
# La vista existe → Loop la usa
```

**(d) Error: pide una vista que no existe:**

```python
history = History()
loop = InstantLoop(agent=A, history=history, view="nonexistent")
# ❌ LoopConfigError al construir
```

Fallar al construir, no al `.run()`. Le ahorra al usuario el ciclo "construye → ejecuta → revienta a mitad de step".

### Resumen de decisiones

| Punto | Decisión |
|---|---|
| Tipo de `history` | `History` instance \| `None` |
| Default de `history` | `None` → Loop crea uno fresco con `History()` |
| Multi-loop sobre la misma instancia | Soportado, pasando la misma instancia |
| History con contenido previo | Soportado, el Loop appendea sin más |
| ¿Loop "posee" el history? | No, lo comparte |
| `view` que no existe y es `"loop_default"` | Loop registra la built-in al construir |
| `view` que no existe y NO es `"loop_default"` | `LoopConfigError` al construir |
| `view` que ya estaba registrada | Loop usa la del usuario, no toca |

---

## Stop conditions — cómo se detiene un Loop

Esta es la sección más importante para entender el flujo de control del Loop. La cubrimos en detalle.

### La idea central

Un Loop puede terminar por **cinco razones distintas**, ordenadas de más a menos común:

| Razón | `terminated_reason` | `stop_reason` (string) |
|---|---|---|
| Una entry de tipo `stop_signal` apareció en el History con texto en la whitelist del Loop | `"stop_signal"` | el `text` del signal |
| El Loop alcanzó `max_steps` sin que nada más lo parara antes | `"max_steps"` | `None` |
| Alguien llamó `loop.stop("...")` desde código externo | `"external"` | el reason pasado |
| La Vista devolvió un `RenderedPrompt` con `stop_reason="..."` | `"view"` | el reason de la View |
| Excepción no recuperable | `"error"` | `None` (la excepción queda en una entry `error`) |

La **primera razón** es la canónica. La conexión con el Monitor que vamos a explicar se basa en ella. Las otras son escapes para casos específicos.

### El flujo de un step — dónde se chequea cada vía

Cada step del Loop sigue exactamente este orden:

```
        step N
          │
          ▼
┌───────────────────────────────────────────────────────────┐
│ (1) Loop renderea: rendered = self.history.export(view)   │
└───────────────────────────────────────────────────────────┘
          │
          ├─── ¿rendered es RenderedPrompt y rendered.stop_reason está set?
          │      sí ──────────────────────────────────────────────┐
          │                                                        ▼
          │                                          STOP — terminated_reason="view"
          │                                                  stop_reason = rendered.stop_reason
          ▼
┌───────────────────────────────────────────────────────────┐
│ (2) Loop appendea step_start                              │
│ (3) Loop llama agent.run(text, images=..., image_detail=) │
│ (4) Bridge: history.append_from_run(...)                  │
│     ─ se appendean: response, tool_call, posible error    │
└───────────────────────────────────────────────────────────┘
          │
          ▼
┌───────────────────────────────────────────────────────────┐
│ (5) Loop invoca su Monitor: self.monitor(self.history)    │
│     ─ las rules evalúan; las que matchean disparan        │
│       acciones; algunas pueden ser stop_signal("X")       │
│       que appendea Entry(type="stop_signal",              │
│                          content={"text": "X"})           │
│     ─ otras acciones pueden hacer side effects (notify,   │
│       persistir a disco, etc.)                            │
└───────────────────────────────────────────────────────────┘
          │
          ▼
┌───────────────────────────────────────────────────────────┐
│ (6) Loop appendea step_end                                │
└───────────────────────────────────────────────────────────┘
          │
          ▼
┌───────────────────────────────────────────────────────────┐
│ (7) Loop escanea entries appendeadas DESPUÉS del run start│
│     - para cada entry con id > _run_start_entry_id:       │
│         si type=="stop_signal" y                          │
│            content["text"] in self.stop_signals:          │
│            → STOP — terminated_reason="stop_signal"       │
│                     stop_reason = content["text"]         │
└───────────────────────────────────────────────────────────┘
          │
          ▼
┌───────────────────────────────────────────────────────────┐
│ (8) Loop chequea su flag interno _stop_requested          │
│     (seteado por loop.stop() desde otro thread/code)      │
│     → STOP — terminated_reason="external"                 │
│              stop_reason = razón pasada a loop.stop()     │
└───────────────────────────────────────────────────────────┘
          │
          ▼
┌───────────────────────────────────────────────────────────┐
│ (9) Loop chequea si step_num >= max_steps                 │
│     → STOP — terminated_reason="max_steps"                │
│              stop_reason = None                           │
└───────────────────────────────────────────────────────────┘
          │
          ▼
        step N+1
```

Cada paso de chequeo es un punto donde el Loop decide si seguir o romper. Si ninguno se cumple, el step pasa al siguiente.

### Vía A — Monitor produce un `stop_signal` (canónico)

Es la forma natural y la que recomendamos. El Monitor evalúa una condición y, si matchea, su acción appendea una entry de tipo `stop_signal` al History. El Loop lo detecta en el paso (7).

**Ejemplo simple — parar si el agente menciona "Pepito":**

```python
from instantneo.monitor import Monitor
from instantneo.actions import stop_signal
from instantneo.conditions import when_response_matches

monitor = Monitor()
monitor.add_rule(
    when_response_matches(r"\bPepito\b"),
    stop_signal("mencionó Pepito"),
)

loop = InstantLoop(
    agent=A,
    history=H,
    monitors=monitor,
    stop_signals=["mencionó Pepito"],   # ← whitelist
)

result = loop.run("contame algo")

result.terminated_reason   # "stop_signal"
result.stop_reason         # "mencionó Pepito"
```

**Lo que pasa internamente, narrativamente:**

1. El Loop renderea el prompt vía la Vista.
2. Llama al agente, que produce una response.
3. El bridge appendea esa response al History.
4. El Loop invoca su Monitor.
5. El Monitor evalúa cada rule en orden:
   - `when_response_matches(r"\bPepito\b")` lee la última response del History. Si encuentra "Pepito", devuelve `True`.
   - El Monitor dispara la action `stop_signal("mencionó Pepito")`.
   - La action hace `history.append(type="stop_signal", content={"text": "mencionó Pepito"})`.
6. El Loop appendea `step_end`.
7. El Loop escanea las entries nuevas. Encuentra una de `type="stop_signal"` con `content["text"] == "mencionó Pepito"`. Como ese string está en `self.stop_signals`, el Loop rompe.
8. `result.stop_reason = "mencionó Pepito"`.

**Múltiples conditions:**

```python
monitor = Monitor()
monitor.add_rule(when_response_matches(r"\bPepito\b"),  stop_signal("mencionó Pepito"))
monitor.add_rule(when_type_present("error"),            stop_signal("error fatal"))
monitor.add_rule(when_tokens_above("loop_default", 100_000), stop_signal("contexto saturado"))

loop = InstantLoop(
    agent=A, history=H, monitors=monitor,
    stop_signals=["mencionó Pepito", "error fatal", "contexto saturado"],
)
```

La que dispare primero gana. `result.stop_reason` te dice cuál fue.

### Vía A.1 — Sugar `stop_tool` (atajo del caso más común)

El caso "parar cuando el agente llamó tal tool" es tan frecuente que hay azúcar:

```python
loop = InstantLoop(agent=A, history=H, stop_tool="finalizar")
```

Internamente equivale a:

```python
loop = InstantLoop(
    agent=A, history=H,
    stop_signals=["agent called finalizar"],
    monitors=Monitor().add_rule(
        when_last_tool_called("finalizar"),
        stop_signal("agent called finalizar"),
    ),
)
```

El kwarg configura **ambos lados**: la whitelist del Loop y la rule del Monitor, con un string canónico (`"agent called {name}"`).

**Múltiples tools:**

```python
loop = InstantLoop(
    agent=A, history=H,
    stop_tool=["finalizar", "abort", "submit"],
)
# Cualquiera de las tres dispara stop, con stop_reason="agent called X".
```

**Combinable con `monitors=`:**

```python
loop = InstantLoop(
    agent=A, history=H,
    stop_tool="finalizar",
    monitors=Monitor().add_rule(
        when_response_matches(r"\bPepito\b"),
        stop_signal("mencionó Pepito"),
    ),
    stop_signals=["mencionó Pepito"],   # las del sugar se agregan automáticamente
)
# El Loop escucha: ["mencionó Pepito", "agent called finalizar"]
# El monitor tiene: la rule de Pepito + la rule auto-generada del stop_tool.
```

### Vía B — `loop.stop(reason)` desde código externo

Si querés cancelar el run desde otro thread, callback, UI, timeout, lo que sea, y tenés referencia al Loop:

```python
import threading

# Cancelar después de 60 segundos:
threading.Timer(60.0, lambda: loop.stop("timeout")).start()

result = loop.run("...")
# Si llega a los 60s:
result.terminated_reason   # "external"
result.stop_reason         # "timeout"
```

**Lo que pasa internamente:**

1. `loop.stop("timeout")` setea un flag interno: `self._stop_requested = True; self._stop_request_reason = "timeout"`.
2. El Loop, al final del step en curso (paso 8 del flujo), chequea ese flag.
3. Si está set, rompe con `terminated_reason="external"`.

**No toca el History.** Es un canal aparte. La razón queda solo en el `RunResult` (a menos que decidas appendear vos mismo una nota antes de llamar `loop.stop`).

### Vía C — Vista devuelve `stop_reason` (avanzado, opcional)

Mecanismo disponible para casos donde la lógica de stop está naturalmente en la Vista. **No es la recomendación principal** — preferí Vía A salvo que tengas una razón concreta para la lógica vivir en la Vista.

```python
from instantneo.loop import RenderedPrompt
from instantneo.loop.default_view import loop_default

@history.view("custom")
def my_view(history):
    rp = loop_default(history)   # arrancar de la default

    # Lógica de stop dentro de la vista:
    responses = history.by_type("response")
    if responses and "Pepito" in responses[-1].content.get("text", ""):
        rp.stop_reason = "mencionó Pepito"

    return rp

loop = InstantLoop(agent=A, history=H, view="custom")
result = loop.run("...")
result.terminated_reason   # "view"
result.stop_reason         # "mencionó Pepito"
```

**Lo que pasa internamente:**

1. El Loop llama `history.export("custom")` al inicio del step.
2. La Vista corre y devuelve `RenderedPrompt(text="...", stop_reason="mencionó Pepito")`.
3. El Loop chequea `rendered.stop_reason` (paso 1 del flujo).
4. Como está set, rompe **antes** de llamar al agente.

**Ventaja única**: la decisión de stop sucede ANTES de gastar la llamada al provider, no después.

**Costos**: la Vista mezcla responsabilidades (renderizado + control). El motivo del stop no queda en el History (solo en el `RunResult`). Difícil de auditar después.

**Cuándo usarla**: rara vez. Si la condición depende de cómo se proyecta el contexto (no del History crudo), y no querés invocar al agente solo para descartar. Casi siempre Vía A es mejor.

### Comparación — qué vía elegir

| Tu situación | Vía recomendada |
|---|---|
| Caso típico: parar por algo del History (response, tool call, error, tokens) | **Vía A — Monitor** |
| Caso ultra-común: parar cuando el agente llama tal tool | **Vía A.1 — sugar `stop_tool`** |
| Cancelación externa (timeout, UI, callback) | **Vía B — `loop.stop()`** |
| Cap defensivo numérico | **`max_steps`** (siempre activo) |
| Lógica de stop integrada con cómo se renderea el prompt | **Vía C — Vista con `stop_reason`** (advanced) |

Las vías son **independientes y combinables**. Podés tener todas a la vez. La que dispare primero gana.

### Ejemplo combinado — todo activo

```python
loop = InstantLoop(
    agent=A,
    history=H,
    monitors=Monitor().add_rule(
        when_type_present("error"),
        stop_signal("error fatal"),
    ),
    stop_signals=["error fatal"],
    stop_tool="finalizar",
    max_steps=50,
)

# Threading externo agregando timeout:
threading.Timer(120.0, lambda: loop.stop("timeout")).start()

result = loop.run("investigá X")

# Posibles outcomes:
#   terminated_reason="stop_signal", stop_reason="error fatal"      → apareció un error
#   terminated_reason="stop_signal", stop_reason="agent called finalizar" → agente llamó la tool
#   terminated_reason="external",    stop_reason="timeout"          → llegaron 120s
#   terminated_reason="max_steps",   stop_reason=None               → 50 steps sin parar
#   terminated_reason="error",       stop_reason=None               → excepción no manejada
```

### Freshness — por qué stop_signals viejos no contaminan runs nuevos

Cuando el Loop arranca un `.run(...)`, recuerda el id de la última entry presente en ese momento (`self._run_start_entry_id`). En el chequeo del paso (7), **solo considera entries con id mayor que ese**. Las viejas se ignoran.

```python
loop = InstantLoop(agent=A, history=H, stop_signals=["finalizar"])

loop.run("tarea 1")
# Durante el run, se appendea Entry(id=15, type="stop_signal", text="finalizar").
# El Loop la detecta (15 > 0), rompe.

loop.run("tarea 2")
# Ahora _run_start_entry_id = 18 (porque el History acumuló 18 entries).
# La entry de id=15 sigue en el History pero 15 ≤ 18 → ignorada.
# El run 2 arranca limpio, sin disparos espurios.
```

**Esto reemplaza el filtrado por `run_id`**. La freshness es más simple y cubre el caso "broadcast a varios Loops" naturalmente: si un código externo appendea un `stop_signal`, todos los Loops que estén corriendo (con el text en su whitelist) lo reciben — porque para todos es "fresco".

### Append directo desde código externo (sin Monitor)

Si tenés acceso al History pero no al Loop, podés appendear directamente:

```python
H.append(
    author="watchdog",
    type="stop_signal",
    content={"text": "necesidad de silencio"},
)
```

Cualquier Loop activo que tenga `"necesidad de silencio"` en su `stop_signals` lo verá y romperá. **Útil para coordinación externa cuando no querés depender de un Monitor compartido.**

### Multi-loop con broadcast — el caso real

```python
loop_inv = InstantLoop(
    name="investigador", history=H,
    stop_signals=["necesidad de silencio", "investigador done"],
)
loop_cri = InstantLoop(
    name="critico", history=H,
    stop_signals=["necesidad de silencio", "critico done"],
)

# Externamente, en algún punto:
H.append(author="external", type="stop_signal",
         content={"text": "necesidad de silencio"})

# Si los dos Loops estaban corriendo, los dos paran con stop_reason="necesidad de silencio".
# Si solo uno está corriendo (otro ya terminó), solo ese para.
```

Para targeting específico (solo a uno), usá strings distintos:

```python
H.append(author="external", type="stop_signal",
         content={"text": "investigador done"})
# Solo loop_inv lo escucha (loop_cri no tiene ese string en su whitelist).
```

### Audit — cómo saber qué pasó después

Después del run, el History tiene la traza completa:

```python
# Todas las stop_signals appendeadas durante el run actual:
fresh_signals = [
    e for e in result.history.all()
    if e.type == "stop_signal" and e.content.get("run_id") == result.run_id
]
for s in fresh_signals:
    print(s.id, s.content["text"])
```

(Las actions del Monitor pueden incluir `run_id` en el content si querés trazabilidad por run; el helper `current_run_id` lo provee. Es opcional — el Loop no requiere `run_id` en el signal porque usa freshness, no run_id matching.)

---

## Vista `loop_default` (registrada al construir el Loop)

El Loop, al instanciarse, registra una vista llamada `loop_default` en su `History` si no existe ya con ese nombre. Esa vista es lo que el agente recibe como prompt en cada turno.

**Carácter**: deliberadamente **simple**. Filtra por `run_id` actual, muestra solo entries narrativas (`prompt`, `response`, `tool_call`), agrupa por turno, formatea markdown. **No procesa entries con `refs` ni types custom** — esos casos requieren una vista distinta opt-in.

### Tipo de retorno: `RenderedPrompt`

Para que la vista controle qué imágenes ve el agente (y no solo el texto), la default devuelve un `RenderedPrompt`:

```python
from dataclasses import dataclass

@dataclass
class RenderedPrompt:
    text:         str                     # texto markdown
    images:       list[str] | None = None # paths/URLs a pasar a agent.run(images=)
    image_detail: str | None = None       # idem image_detail de InstantNeo
```

El Loop, al recibir un `RenderedPrompt`, hace `agent.run(text, images=..., image_detail=...)` con lo que la vista indique. Si una vista custom devuelve solo `str`, el Loop manda `text` sin imágenes.

### Implementación

```python
def loop_default(
    history: History,
    *,
    show_all_runs: bool = False,
    image_policy: Literal["every_turn", "first_only", "none"] = "every_turn",
) -> RenderedPrompt:
    """Vista default del Loop. Texto markdown + imágenes que el agente recibe cada turno.

    Comportamiento de texto:
      - Filtra por run_id actual salvo que show_all_runs=True.
      - Solo incluye entries narrativas: prompt, response, tool_call.
      - Renderea reasoning del response (extended thinking) como bloque distinguible.
      - Renderea tool args/results como JSON pretty (sin extracción especial).
      - Agrupa por turno con header inicial y warning de último turno.

    Comportamiento de imágenes:
      Las imágenes viven en la entry `prompt` del run actual (con paths/URLs,
      no base64). Esta vista las incluye en el RenderedPrompt según `image_policy`:

        - "every_turn" (default, matching legacy): incluye en cada step.
        - "first_only":                            solo en step 1.
        - "none":                                  nunca (la vista las ignora).

      El texto siempre menciona las refs ("imágenes adjuntas: img_1, ...") aunque
      no las pase, así el modelo "sabe" que hubo imágenes.

    Args:
        history: El History del que leer.
        show_all_runs: Si True, ignora el filtro de run_id actual.
        image_policy: Política de inclusión de imágenes en el RenderedPrompt.
    """
    rid = current_run_id(history)
    entries = [
        e for e in history.all()
        if (show_all_runs or e.content.get("run_id") == rid)
        and e.type in {"prompt", "response", "tool_call"}
    ]

    cfg = current_run_config(history) or {}
    max_steps = cfg.get("loop", {}).get("max_steps", "?")
    current_step = current_step_num(history) or 0

    text = _markdown_format_default(
        entries,
        current_step=current_step,
        max_steps=max_steps,
    )

    # Decidir qué imágenes incluir
    images, image_detail = None, None
    prompt_entry = next(
        (e for e in entries if e.type == "prompt" and e.content.get("run_id") == rid),
        None,
    )
    if prompt_entry and prompt_entry.content.get("images"):
        send_now = (
            image_policy == "every_turn"
            or (image_policy == "first_only" and current_step == 1)
        )
        if send_now:
            images = [img["source"] for img in prompt_entry.content["images"]]
            image_detail = prompt_entry.content.get("image_detail")

    return RenderedPrompt(text=text, images=images, image_detail=image_detail)
```

`_markdown_format_default` (en `instantneo/loop/default_view.py`):
- Header con turno actual y total ("Estás en el turno 3 de 30").
- Si la entry `prompt` tiene imágenes, las menciona como referencias textuales (ej. "imágenes adjuntas: img_1, img_2"). NO embebe data binaria.
- Wrapper `<historial>...</historial>`.
- Por cada step, sección `## Turno N` con:
  - `### reasoning` (bloque distinguible) si `content["reasoning"]` está poblado.
  - `### assistant:` con el `text`.
  - Tools con args y result como JSON pretty, sin extracciones especiales.
- Warning en último turno (forzar conclusión).
- Cierre con instrucción de razonamiento.

### Parámetros de la vista

| Param | Tipo | Default | Rol |
|---|---|---|---|
| `show_all_runs` | `bool` | `False` | Si True, no filtra por run_id actual |
| `image_policy` | `"every_turn" \| "first_only" \| "none"` | `"every_turn"` | Cuándo incluir las imágenes en el RenderedPrompt |

Casos típicos:

```python
# Multi-run sobre el mismo History, agente ve todo el contexto histórico:
history.add_view("loop_default", lambda h: loop_default(h, show_all_runs=True))

# Optimizar tokens: imagen solo en primer turno:
history.add_view("loop_default", lambda h: loop_default(h, image_policy="first_only"))

# Combinación:
history.add_view("loop_default",
                 lambda h: loop_default(h, show_all_runs=True, image_policy="none"))
```

Si necesitás algo distinto a estos ejes, registrás una vista custom desde cero.

### Override por el user

```python
@history.view("loop_default")
def my_custom_default(history):
    ...
    return RenderedPrompt(text=..., images=..., image_detail=...)

loop = InstantLoop(agent=A, history=history)   # usa la mía
```

O usa otro nombre y lo pasa al constructor:

```python
@history.view("for_a_special")
def for_a_special(history):
    ...

loop = InstantLoop(agent=A, history=history, view="for_a_special")
```

### Custom view: ejemplo "incluir imágenes que appendeó otro agente"

Caso multiagente — uno hace una tool call que devuelve una imagen, querés que el siguiente agente la vea:

```python
@history.view("incluir_imagenes_de_tools")
def view_full(history):
    rid = current_run_id(history)
    entries = [
        e for e in history.all()
        if e.content.get("run_id") == rid
        and e.type in {"prompt", "response", "tool_call"}
    ]

    text = _markdown_format_default(entries, ...)

    # Recoger imágenes de cualquier source: prompt + tool results
    images = []
    for e in entries:
        if e.type == "prompt" and e.content.get("images"):
            images.extend(img["source"] for img in e.content["images"])
        elif e.type == "tool_call":
            result = e.content.get("result", {})
            if isinstance(result, dict) and "image_url" in result:
                images.append(result["image_url"])

    return RenderedPrompt(text=text, images=images or None)

loop = InstantLoop(agent=B, history=history, view="incluir_imagenes_de_tools")
```

La View es la fuente única de lo que el agente ve.

---

## Entries operacionales que emite el Loop

Todas con `author="orchestrator"`. Toda entry escrita durante un `loop.run()` lleva `origin` (= `self.name`) y `run_id` en su `content` (incluyendo las que emite el bridge — ver `runinfo-to-entries.md`).

### `run_start`

Emitida una vez al inicio de `loop.run()`. Concentra TODA la cabecera (config del agente + config del Loop) para reproducibilidad.

```python
content = {
    "origin":  str,                      # name del Loop (estable entre runs)
    "run_id":     str,                      # uuid generado para esta invocación
    "started_at": str,                      # ISO 8601 UTC

    "agent": {
        "name":                 str,                  # agent.name si existe, sino "agent"
        "provider":             str,
        "model":                str,                  # default del agente
        "role_setup":           str,                  # system prompt original (de InstantNeoConfig)
        "role_setup_resolved":  str,                  # system prompt final efectivo
                                                       # (role_setup + tool_instructions + shelf_context si los hay)
        "tools": [                                     # schemas completos, no solo nombres
            {
                "name":        str,                    # nombre de la tool
                "description": str,                    # docstring / descripción
                "parameters":  dict,                   # JSON Schema de parameters
            },
            ...
        ],
        "defaults": {                                  # de InstantNeoParams, sin secrets
            "temperature":       float | None,
            "max_tokens":        int | None,
            "presence_penalty":  float | None,
            "frequency_penalty": float | None,
            "stop":              str | list | None,
            "seed":              int | None,
            "stream":            bool,
            "image_detail":      str | None,
            # ... cualquier otro kwarg que tenga default en el agente
        },
    },

    "loop": {
        "max_steps":     int,                # 0 = sin cap
        "view":          str,                # nombre de la vista usada
        "stop_signals":  list[str],          # whitelist que el Loop escucha
        "stop_tool":     list[str] | None,   # tools cuya invocación dispara stop (resuelto a lista)
        "monitor_rules": list[str],          # nombres de reglas registradas en self.monitor (si tienen)
        "debug":         bool,
    },
}
```

**Lo que NO incluye**: `api_key`, `service_account_file`, `location`, versión de la lib (eso a logs).

### `prompt` del usuario

Emitida después del `run_start`, una vez por `loop.run()`, antes del primer step. Captura el prompt que el caller pasó y las imágenes asociadas.

```python
Entry(
    author="user",
    type="prompt",
    content={
        "text":         str,                # el prompt
        "images":       list[dict] | None,  # refs/datos de imagen, si hubo
        "image_detail": str | None,
        "origin":    str,
        "run_id":       str,
    },
)
```

### `step_start`

Emitida al inicio de cada step.

```python
content = {
    "origin":  str,
    "run_id":     str,
    "step_num":   int,                      # 1-indexed
}
```

### `step_end`

Emitida al final de cada step, después de invocar el Monitor pero antes del próximo `step_start`.

```python
content = {
    "origin":   str,
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
    "origin":      str,
    "run_id":         str,
    "step_num":       int,
    "exception":      str,
    "exception_type": str,                  # type(e).__name__
    "context":        str,                   # "monitor_action", "agent.run", etc.
}
```

### `stop_signal` — el contrato

El Loop **NO la emite**. La appendean: actions del Monitor (típicamente `stop_signal(text)`), código externo, o tools. El Loop la **lee** para decidir si parar.

Shape canónico (mínimo):

```python
content = {
    "text": str,        # el string que el Loop matchea contra self.stop_signals
}
```

Shape con audit opcional (recomendado cuando producís manual o desde code custom):

```python
content = {
    "text":       str,
    "origin":     str,          # quién la produjo (loop_name si Monitor, "external" si manual)
    "run_id":     str,          # opcional: helps post-mortem queries
    "extra":      dict | None,  # opcional: cualquier metadata de tu dominio
}
```

El Loop **solo lee `content["text"]`** y compara con `self.stop_signals`. Los campos extra son convención del usuario para auditoría posterior.

Ver sección "Stop conditions" para el flujo completo y todos los casos.

### `run_end`

Emitida al cierre de `loop.run()`, sin importar la razón de terminación.

```python
content = {
    "origin":            str,
    "run_id":            str,
    "completed_at":      str,
    "duration_s":        float,
    "terminated_reason": str,                # "stop_signal" | "view" | "external" | "max_steps" | "error"
    "stop_reason":       str | None,         # texto específico que disparó (None si max_steps/error)
    "total_steps":       int,                # cuántos steps corrieron
}
```

### Sin entry `llm_debug` — la data pesada va al `RunLog`

**Decisión de diseño**: el History se mantiene lean siempre. La data pesada de debug (prompt rendered, messages_sent literal, detalle per-LLM-call) **no se appendea al History** aunque `debug=True`. Vive en un objeto separado, el `RunLog`, que se persiste a un folder en disco. Ver `log-design.md`.

Esto evita que `debug=True` infle el History de modo desproporcionado y mantiene la separación de responsabilidades:
- **History**: lo operacional, lo que el agente y observabilidad casual necesitan.
- **RunLog**: lo forense, para replay/audit/análisis profundo.

---

## Flujo de `run()` paso a paso

```python
def run(
    self,
    prompt: str,
    *,
    images: str | list[str] | None = None,
    image_detail: str | None = None,
) -> RunResult:
    run_id = uuid.uuid4().hex
    self._current_run_id = run_id
    self._stop_requested = False
    self._stop_request_reason = None
    started_at = time.time()
    started_at_iso = datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat()
    terminated_reason = None
    stop_reason = None
    total_steps = 0

    # 0. Si debug=True, construir el RunLog (delega a helper en instantneo/loop/debug.py)
    log = None
    if self.debug:
        self._run_counter += 1
        log = _new_run_log_for_loop(self, run_id, started_at_iso, prompt, images, image_detail)
        log.write_config()

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
            "text":         prompt,
            "images":       _refs_from(images),
            "image_detail": image_detail,
            "origin":       self.name,
            "run_id":       run_id,
        },
    )

    # 3.b Snapshot del último id presente — usado para freshness de stop_signals
    self._run_start_entry_id = (
        self.history.all()[-1].id if self.history.all() else 0
    )

    # 4. Loop de steps. max_steps=0 significa sin cap.
    step_num = 0
    while True:
        step_num += 1
        if self.max_steps != 0 and step_num > self.max_steps:
            terminated_reason = "max_steps"
            total_steps = step_num - 1
            break

        step_start_time = time.perf_counter()

        # 4.a Render del prompt vía vista
        # La Vista puede devolver str (solo texto) o RenderedPrompt (texto + imágenes + posible stop).
        rendered = self.history.export(self.view)

        if isinstance(rendered, RenderedPrompt):
            # 4.a.1 — Vía Vista: si la vista pidió stop, romper antes de gastar el agente
            if rendered.stop_reason:
                terminated_reason = "view"
                stop_reason = rendered.stop_reason
                total_steps = step_num - 1
                break

            text_to_send = rendered.text
            images_to_send = rendered.images
            image_detail_to_send = rendered.image_detail
        elif isinstance(rendered, str):
            text_to_send = rendered
            images_to_send = None
            image_detail_to_send = None
        else:
            raise TypeError(
                f"View '{self.view}' devolvió {type(rendered).__name__}, "
                f"esperado: str o RenderedPrompt"
            )

        # 4.b step_start
        self.history.append(
            author="orchestrator",
            type="step_start",
            content={"origin": self.name, "run_id": run_id, "step_num": step_num},
        )
        step_started_iso = datetime.utcnow().isoformat()

        # 4.c agent.run() — captura excepciones a nivel run
        try:
            self.agent.run(text_to_send,
                           images=images_to_send,
                           image_detail=image_detail_to_send)
        except Exception as e:
            if self.agent.last_run is None or self.agent.last_run.error is None:
                self.history.append(
                    author="orchestrator",
                    type="error",
                    content={
                        "origin":         self.name,
                        "run_id":         run_id,
                        "step_num":       step_num,
                        "exception":      str(e),
                        "exception_type": type(e).__name__,
                        "context":        "agent.run",
                    },
                )
                terminated_reason = "error"
                break

        # 4.d Bridge: descomponer last_run en entries (con origin y run_id).
        append_entry_from_run(
            self.history,
            self.agent.last_run,
            turn_num=step_num,
            author=self.agent.name or "agent",
            origin=self.name,
            run_id=run_id,
        )

        # 4.e Si debug, appendear el TurnLog al RunLog (escribe turn_NNN.json a disco).
        # El History NO se contamina con data pesada.
        if log is not None and self.agent.last_run:
            turn = TurnLog.from_runinfo(
                step_num=step_num,
                started_at=step_started_iso,
                completed_at=datetime.utcnow().isoformat(),
                run_info=self.agent.last_run,
            )
            log.append_turn(turn)    # escribe turn_NNN.json internamente

        # 4.f Invocar el Monitor del Loop
        # (sus actions pueden appendear stop_signal, notes, etc., y/o hacer side effects)
        try:
            self.monitor(self.history)
        except Exception as e:
            self.history.append(
                author="orchestrator",
                type="error",
                content={
                    "origin":         self.name,
                    "run_id":         run_id,
                    "step_num":       step_num,
                    "exception":      str(e),
                    "exception_type": type(e).__name__,
                    "context":        "monitor_action",
                },
            )
            terminated_reason = "error"
            break

        # 4.g step_end
        self.history.append(
            author="orchestrator",
            type="step_end",
            content={
                "origin":      self.name,
                "run_id":      run_id,
                "step_num":    step_num,
                "duration_ms": (time.perf_counter() - step_start_time) * 1000,
            },
        )

        # 4.h — Vía Monitor / append externo:
        # Buscar stop_signal frescas (id > snapshot) cuyo text esté en la whitelist.
        signal = self._find_fresh_stop_signal()
        if signal:
            terminated_reason = "stop_signal"
            stop_reason = signal.content["text"]
            total_steps = step_num
            break

        # 4.i — Vía externa: chequear flag de loop.stop()
        if self._stop_requested:
            terminated_reason = "external"
            stop_reason = self._stop_request_reason
            total_steps = step_num
            break

        total_steps = step_num

    # 5. run_end (siempre, con la razón final)
    completed_at = time.time()
    completed_at_iso = datetime.fromtimestamp(completed_at, tz=timezone.utc).isoformat()
    self.history.append(
        author="orchestrator",
        type="run_end",
        content={
            "origin":            self.name,
            "run_id":            run_id,
            "completed_at":      completed_at_iso,
            "duration_s":        completed_at - started_at,
            "terminated_reason": terminated_reason,
            "stop_reason":       stop_reason,
            "total_steps":       total_steps,
        },
    )

    # 6. Si debug, cerrar el RunLog (escribe run_end.json a disco)
    if log is not None:
        log.completed_at = completed_at_iso
        log.terminated_reason = terminated_reason
        log.stop_reason = stop_reason
        log.write_run_end()

    return RunResult(
        history=self.history,
        name=self.name,
        run_id=run_id,
        terminated_reason=terminated_reason,
        stop_reason=stop_reason,
        duration_s=completed_at - started_at,
        total_steps=total_steps,
        log=log,                # None si debug=False, RunLog si debug=True
    )


def _find_fresh_stop_signal(self) -> Entry | None:
    """Devuelve la primera entry stop_signal appendeada después del run start
    cuyo text matchea con self.stop_signals. None si no hay."""
    if not self.stop_signals:
        return None
    for e in self.history.all():
        if e.id <= self._run_start_entry_id:
            continue
        if e.type != "stop_signal":
            continue
        if e.content.get("text") in self.stop_signals:
            return e
    return None


def stop(self, reason: str = "external") -> None:
    """Cancela el run en curso. Pone un flag interno; el Loop rompe al final
    del step actual con terminated_reason='external' y stop_reason=reason."""
    self._stop_requested = True
    self._stop_request_reason = reason
```

---

## Helpers necesarios

Viven en `instantneo/history/queries.py`. Las built-in actions y conditions los usan; el user puede usarlos en sus rules custom.

### `current_run_config(history) -> dict | None`

Devuelve el `content` de la entry `run_start` más reciente, o `None`. Útil para que conditions/actions del Monitor accedan a la cabecera sin escarbar.

```python
def current_run_config(history):
    starts = history.by_type("run_start")
    return starts[-1].content if starts else None
```

### `current_run_id(history) -> str | None`

Devuelve el `run_id` del `run_start` más reciente.

### `current_origin(history) -> str | None`

Devuelve el `origin` del `run_start` más reciente. Útil para auditoría: "¿qué orquestador produjo esta entry?".

### `current_step_num(history) -> int | None`

Devuelve el `step_num` del `step_start` más reciente del run actual. Lo necesitan conditions tipo `every_n_steps`.

> **Limitación de uso**: estos helpers funcionan correctamente en uso **secuencial** (un solo `loop.run()` activo a la vez sobre un History dado). Para escenarios concurrentes (dos Loops escribiendo al mismo History en paralelo), retornarían el último `run_start` que esté presente, que puede no ser el del Loop que invoca. Concurrencia real queda fuera de scope para v1; cuando se implemente, los helpers deberán recibir contexto explícito o usar `contextvars`.

---

## Integración con Monitor

El Loop **tiene su propio Monitor** en `self.monitor`, construido del param `monitors=` con el mismo patrón que `InstantNeo` con `tools=`:

| `monitors=` | `self.monitor` resultante |
|---|---|
| `Monitor` instance | la misma instancia (mutaciones se propagan) |
| `list[Monitor]` | `MonitorOperations.union(*monitors)` (snapshot) |
| `None` o ausente | `Monitor()` vacío |

En cada step, post-bridge, el Loop ejecuta `self.monitor(self.history)` una sola vez.

```python
monitor = Monitor()
monitor.add_rule(every_n_steps(10),              append_note("checkpoint"))
monitor.add_rule(when_type_present("error"),     stop_signal("err"))

history = History()
loop = InstantLoop(agent=A, history=history, monitors=monitor, max_steps=30)

loop.run("investigá X")
# Cada step, después del bridge, self.monitor(self.history) corre las reglas.
# Si alguna registra stop_signal con este run_id, el Loop rompe en el chequeo siguiente.
```

Si no se pasa `monitors=`, el Loop tiene un Monitor vacío. El caller puede agregar reglas después con `loop.monitor.add_rule(...)`.

El detalle de la sugar `stop_tool`, las whitelists de `stop_signals`, el método `loop.stop()` y la Vía View — todos están en la sección **"Stop conditions"** más arriba. Esta sección de "Integración con Monitor" cubre solo el rol del Monitor en sí.

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
        # `stop_tool=` legacy mantiene su nombre — coincide con el nuevo
        self._impl = NewInstantLoop(
            agent=agent,
            max_steps=max_turns,
            debug=bool(debug_dir),
            stop_tool=stop_tool,
        )
        self._debug_dir = debug_dir
        self._agent_config = agent_config
        self._images = images
        self._image_detail = image_detail

    def run(self, prompt):
        result = self._impl.run(
            prompt,
            images=self._images,
            image_detail=self._image_detail,
        )
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

- `test_loop_constructor_with_default_name_autogenerates_id`
- `test_loop_constructor_with_explicit_name_uses_it`
- `test_loop_constructor_with_no_monitors_creates_empty_monitor`
- `test_loop_constructor_with_single_monitor_uses_same_instance`
- `test_loop_constructor_with_list_of_monitors_uses_union`
- `test_loop_run_emits_run_start_with_full_config`
- `test_loop_run_emits_prompt_entry_after_run_start_with_images`
- `test_loop_run_emits_step_start_step_end_per_step`
- `test_loop_run_calls_append_entry_from_run_with_origin_and_run_id`
- `test_loop_run_invokes_monitor_per_step`
- `test_loop_stops_on_stop_signal_for_this_run_id`
- `test_loop_stops_on_max_steps_when_no_stop_signal`
- `test_loop_handles_run_error_via_bridge`
- `test_loop_emits_run_end_with_terminated_reason`
- `test_loop_default_view_filters_operational_entries`
- `test_loop_with_custom_view_uses_custom`
- `test_loop_with_debug_true_creates_runlog_in_result`
- `test_loop_with_debug_true_writes_folder_structure`
- `test_loop_with_debug_false_returns_log_none`
- `test_history_unchanged_with_debug_true_vs_false` — confirma que el History es idéntico con o sin debug
- `test_loop_with_existing_history_appends_run_start_per_run`   # multi-run
- `test_all_emitted_entries_carry_origin_and_run_id`

Tests de stop conditions:

- `test_stop_signal_via_monitor_appendea_entry_y_loop_para`
- `test_stop_signal_via_external_append_funciona_aunque_no_haya_monitor`
- `test_stop_tool_string_auto_configura_whitelist_y_rule`
- `test_stop_tool_list_registra_multiples_rules`
- `test_loop_stop_metodo_setea_flag_y_corta_run`
- `test_view_stop_reason_corta_antes_de_agent_run`
- `test_freshness_ignora_stop_signals_de_runs_anteriores`
- `test_max_steps_cap_dispara_solo_si_no_hubo_otra_via`
- `test_max_steps_cero_significa_sin_cap`

Tests de integración con un Monitor con reglas reales:

- `test_loop_with_monitor_append_note_every_n_appends_note`
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
   - Implementar helpers `current_run_config`, `current_run_id`, `current_origin`, `current_step_num` en `queries.py`.
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

- **Tool opt-in `recall_image`**: cuando una vista no incluye la imagen (ej. `image_policy="first_only"` o `"none"`) y el agente "recuerda" en un step posterior que existió pero no la ve, hoy no tiene forma de re-mirarla. Una built-in tool tipo `recall_image(image_id)` que devuelva el image content block multimodal podría dar agencia al agente. No bloquea el MVP — queda como issue futura.

- **Concurrencia / async**: hoy todo es síncrono. Async support es feature futura, no bloquea el MVP del Loop. Cuando llegue, los helpers `current_*` necesitarán contexto explícito o `contextvars` (ver limitación documentada en sección de Helpers).

- **Persistencia del History entre runs**: ya está soportada por el design (multi-run sobre un History reutilizado). Subclases tipo `FileHistory`, `RedisHistory` quedan como issue futura.

- **Locking del History bajo concurrencia**: si actions registradas en el Monitor del Loop disparan threads de fondo que appendean al History, hay race conditions en `History.append`. Solución (cuando se necesite): un `threading.Lock` en `append`. No bloquea la v1, solo se vuelve crítico si se documenta el patrón de actions en background como soportado.
