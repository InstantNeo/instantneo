# Refactor: unificación de los providers Vertex

## Resumen ejecutivo

Reorganización interna de los providers hosteados en Vertex AI (Anthropic Claude y Google Gemini) bajo un único patrón claro: cada Vertex+X es un fetcher delgado que **hereda** del fetcher directo y un adapter delgado que **hereda** del adapter directo. Auth GCP centralizada en `fetchers/vertex/_auth.py`. Se elimina la duplicación de código entre `vertexai.py` y `gemini.py`, y entre `vertex_anthropic.py` y `anthropic.py`. **La API pública de `InstantNeo(...)` no cambia** — todo el código de usuario que invoque `InstantNeo(provider="vertex_anthropic", ...)` o `InstantNeo(provider="vertexai", ...)` sigue funcionando idéntico.

## Motivación

Cinco problemas concretos en el estado anterior:

1. **Duplicación masiva.** `instantneo/fetchers/vertexai.py` (622 líneas) era un fork prácticamente byte a byte de `instantneo/fetchers/gemini.py`: `_build_request_body`, `_parse_response` y `_part_to_dict` estaban literalmente repetidos. Cualquier fix en `gemini.py` no se propagaba a `vertexai.py`.

2. **Pérdida silenciosa de capacidades.** `instantneo/fetchers/vertex_anthropic.py` reimplementaba ~70% de `anthropic.py` y se le habían quedado fuera **cuatro parámetros** que sí soporta el master Anthropic: `container`, `context_management`, `mcp_servers`, `service_tier`. Pasarlos por `InstantNeo(...)` con `provider="vertex_anthropic"` los descartaba sin error, sin warning.

3. **Bug latente en streaming.** En `vertex_anthropic.py:221`, dentro de `create_message`, la llamada a `_build_request_body(...)` hardcodeaba `stream=False` aun cuando el método público aceptaba `stream` en su firma. Pedir streaming via Vertex Anthropic devolvía no-stream (o, en el peor caso, fallaba al parsear).

4. **Acoplamiento espurio entre fetchers hermanos.** `vertex_anthropic.py:23` importaba funciones privadas (`_create_jwt`, `_exchange_jwt_for_token`, `_load_service_account`) directamente desde `vertexai.py`. Dos fetchers que no tienen relación de dominio (uno habla con Claude, otro con Gemini) no deberían depender entre sí.

5. **Asimetría de patrón.** Para Anthropic-en-Vertex existía un adapter wrapper separado (`vertex_anthropic_adapter.py`, 36 líneas, patrón limpio). Para Gemini-en-Vertex se había metido branching interno dentro del propio `GeminiAdapter` (un `if api_key: ... elif service_account: ...` en el constructor). Dos formas distintas de resolver el mismo problema, sin regla clara para futuros providers Vertex (Llama, Mistral, etc.).

## Decisión arquitectónica

Se reconoce explícitamente que **Vertex es una capa de transporte** (auth GCP + construcción de endpoint + formato SSE), **ortogonal al provider** (shape de mensajes, tools, parsing, streaming protocol). La lógica del provider es ~95% idéntica entre la API directa y Vertex; lo único que cambia es el transporte. El estado anterior mezclaba ambas preocupaciones y terminaba forkeando el provider entero cada vez que se añadía un Vertex.

La nueva organización separa los dos ejes:

- **Eje provider** (vive en `fetchers/anthropic.py`, `fetchers/gemini.py`, etc.): cómo se construye el body, cómo se parsea la respuesta, cómo se itera el streaming, qué parámetros acepta.
- **Eje transporte** (vive en `fetchers/vertex/_auth.py`): cómo se autentica con GCP, cómo se construye la URL del endpoint Vertex, cómo se firman los JWTs.

Cada cliente concreto compone los dos ejes via herencia múltiple:

```python
class VertexAnthropicClient(VertexAuthMixin, AnthropicClient):
    PUBLISHER = "anthropic"
    ANTHROPIC_VERSION = "vertex-2023-10-16"
    # 3 overrides pequeños: __init__, _build_headers, _get_url, _build_request_body
```

`create_message`, `create_message_stream`, `_parse_response` se heredan tal cual del fetcher directo. **El fix de los 4 parámetros perdidos y el bug de streaming** llegan gratis por ese mismo mecanismo: el body builder y el flujo de streaming los aporta `AnthropicClient`, que sí los soporta correctamente.

## Patrón unificado para futuros Vertex

Receta concreta de tres pasos para añadir un nuevo provider hospedado en Vertex (por ejemplo `vertex_llama`):

1. **Fetcher** — crear `instantneo/fetchers/vertex/llama.py`:
   ```python
   from instantneo.fetchers.llama import LlamaClient
   from instantneo.fetchers.vertex._auth import VertexAuthMixin

   class VertexLlamaClient(VertexAuthMixin, LlamaClient):
       PUBLISHER = "meta"  # según el publisher Vertex correspondiente

       def __init__(self, location, service_account_file=None, ...):
           VertexAuthMixin.__init__(self, location=location, ...)

       def _build_headers(self):
           return self._build_vertex_headers()

       def _get_url(self, model, stream=False):
           action = "..."  # según endpoint Vertex del publisher
           return self._vertex_endpoint(self.PUBLISHER, model, action)
   ```

2. **Adapter** — crear `instantneo/adapters/vertex_llama_adapter.py`:
   ```python
   from instantneo.adapters.llama_adapter import LlamaAdapter
   from instantneo.fetchers.vertex.llama import VertexLlamaClient

   class VertexLlamaAdapter(LlamaAdapter):
       def __init__(self, location, service_account_file=None, ...):
           self.client = VertexLlamaClient(location=location, ...)

       def get_provider_name(self) -> str:
           return "vertex_llama"
   ```

3. **Registro** — añadir entrada en `core.py:_create_adapter`:
   ```python
   "vertex_llama": ("instantneo.adapters.vertex_llama_adapter", "VertexLlamaAdapter"),
   ```

   Y, si el provider directo `LlamaClient` aún no expone un hook tipo `_get_url(model)` (porque internamente accede a `BASE_URL` directo), añadirlo igual que ya se hizo con `AnthropicClient`.

Requisito mínimo del fetcher directo: exponer un método `_get_url` o `_get_endpoint` que la subclase Vertex pueda sobrescribir, y aceptar la inyección de headers vía `_build_headers`. Es lo único que necesita ser "Vertex-friendly" en la clase base.

## Cambios por archivo

| Archivo | Cambio | Motivo |
|---|---|---|
| `instantneo/fetchers/vertex/__init__.py` | Nuevo | Subpaquete que agrupa los providers Vertex |
| `instantneo/fetchers/vertex/_auth.py` | Nuevo | `VertexAuthMixin` + helpers JWT/OAuth/SA, antes duplicados |
| `instantneo/fetchers/vertex/anthropic.py` | Nuevo | `VertexAnthropicClient(VertexAuthMixin, AnthropicClient)` |
| `instantneo/fetchers/vertex/gemini.py` | Nuevo | `VertexGeminiClient(VertexAuthMixin, GeminiClient)` |
| `instantneo/fetchers/anthropic.py` | Modificado | Añade hook `_get_url(model, stream)`; sustituye dos usos de `self.BASE_URL` |
| `instantneo/fetchers/__init__.py` | Modificado | Exporta los dos nuevos clients desde el subpaquete `vertex` |
| `instantneo/fetchers/vertex_anthropic.py` | Borrado | Reemplazado por `vertex/anthropic.py` |
| `instantneo/fetchers/vertexai.py` | Borrado | Reemplazado por `vertex/gemini.py` |
| `instantneo/adapters/vertex_gemini_adapter.py` | Nuevo | Subclase delgada paralela a `vertex_anthropic_adapter.py` |
| `instantneo/adapters/gemini_adapter.py` | Modificado | `__init__` simplificado: solo `api_key`. Eliminado branching interno y atributo `_backend` |
| `instantneo/adapters/vertex_anthropic_adapter.py` | Modificado | Una sola línea: nuevo path de import |
| `instantneo/adapters/__init__.py` | Modificado | Añade try-import de `VertexGeminiAdapter` |
| `instantneo/core.py` | Modificado | `adapter_map["vertexai"]` apunta ahora a `VertexGeminiAdapter` |

## Bugs corregidos

- **Streaming de Vertex Anthropic ahora funciona.** Antes, el `stream=False` hardcodeado dentro de `_build_request_body()` dejaba el body sin la flag aunque el caller pidiera streaming. Tras el refactor, `create_message_stream` se hereda de `AnthropicClient`, que pasa `stream=True` correctamente.
- **Vertex Anthropic acepta `container`, `context_management`, `mcp_servers`, `service_tier`.** Estos cuatro parámetros eran soportados por `AnthropicClient` pero no por `VertexAnthropicClient`. Al heredar `_build_request_body` y `create_message` del padre, se incluyen automáticamente. El refactor incluye un test de construcción de body que confirma su presencia.
- **`vertex_anthropic` deja de depender de `vertexai`.** La auth GCP vive ahora en `fetchers/vertex/_auth.py`, módulo común a ambos. Cualquier cambio futuro en JWT/OAuth se hace en un único lugar.

## Compatibilidad

**API pública de `InstantNeo` (lo que ven los usuarios del paquete): idéntica.** Todos estos invocaciones siguen funcionando sin cambio:

```python
InstantNeo(provider="anthropic", api_key="sk-ant-...", ...)
InstantNeo(provider="gemini", api_key="AIza...", ...)
InstantNeo(provider="vertex_anthropic", location="us-east5", service_account_file="...", ...)
InstantNeo(provider="vertexai", location="us-central1", service_account_file="...", ...)
```

**Imports internos** (solo afecta a quien instancie clientes/adapters fuera de `core.py`):

| Antes | Ahora |
|---|---|
| `from instantneo.fetchers.vertex_anthropic import VertexAnthropicClient` | `from instantneo.fetchers.vertex.anthropic import VertexAnthropicClient` |
| `from instantneo.fetchers.vertexai import VertexAIClient` | `from instantneo.fetchers.vertex.gemini import VertexGeminiClient` |
| `from instantneo.fetchers import VertexAnthropicClient` | (sigue funcionando) |
| `from instantneo.fetchers import VertexGeminiClient` | (nuevo, también disponible) |

**`GeminiAdapter` directo:** la firma anterior `GeminiAdapter(location=..., service_account_file=..., ...)` ya **no** se acepta. La búsqueda en el código del repositorio confirmó que ningún call site externo a `core.py` la usaba. Quien la necesite ahora debe usar `VertexGeminiAdapter(...)` o, mejor, `InstantNeo(provider="vertexai", ...)`.

## Cómo revisar el PR

Orden de lectura sugerido para que el cambio se entienda incrementalmente:

1. **`instantneo/fetchers/vertex/_auth.py`** — la nueva base compartida. Es esencialmente el código que vivía en `vertexai.py:42-173` movido a un módulo propio, más una clase `VertexAuthMixin` que encapsula auth + endpoint + headers.
2. **`instantneo/fetchers/anthropic.py`** — los dos cambios mínimos en el master: nuevo método `_get_url()` (devuelve `BASE_URL` por defecto) y dos usos de `self.BASE_URL` reemplazados por `self._get_url(model)`. Comportamiento idéntico al previo.
3. **`instantneo/fetchers/vertex/anthropic.py`** y **`vertex/gemini.py`** — los dos clientes Vertex nuevos. Cada uno son ~40 líneas que solo declaran las diferencias reales con su master directo.
4. **`instantneo/adapters/gemini_adapter.py`** — simplificación del `__init__` (eliminación del branching).
5. **`instantneo/adapters/vertex_gemini_adapter.py`** y **`vertex_anthropic_adapter.py`** — el primero es nuevo y paralelo al segundo (que ya existía y casi no cambia). El segundo solo actualiza la ruta de import.
6. **`instantneo/core.py`** — un único cambio en el `adapter_map`.

## Cómo verificar localmente

Las pruebas de humo automáticas (sin requerir credenciales reales) ya están corridas durante el desarrollo y se documentan aquí para que el reviewer pueda repetirlas:

```bash
.venv/bin/python -c "
from instantneo.fetchers.vertex import VertexAnthropicClient, VertexGeminiClient
from instantneo.fetchers.vertex._auth import VertexAuthMixin

# 1. Imports nuevos funcionan
# 2. Las rutas viejas fallan
import importlib
for old in ('instantneo.fetchers.vertex_anthropic', 'instantneo.fetchers.vertexai'):
    try:
        importlib.import_module(old); print(f'FAIL: {old} sigue importable')
    except ImportError:
        print(f'OK: {old} borrado')

# 3. MRO correcto
print('VertexAnthropicClient MRO:', [c.__name__ for c in VertexAnthropicClient.__mro__])

# 4. URL Vertex bien construida
va = VertexAnthropicClient(location='us-east5', access_token='fake'); va.project_id='proj'
print('URL:', va._get_url('claude-foo'))
print('URL stream:', va._get_url('claude-foo', stream=True))

# 5. Body con los 4 params restaurados + anthropic_version
from instantneo.models.anthropic import Message
body = va._build_request_body(
    model='claude-foo', messages=[Message(role='user', content='hi')], max_tokens=10,
    service_tier='auto', container='c-1', context_management={'mode':'auto'},
    mcp_servers=[{'url':'https://x'}],
)
assert 'model' not in body
assert body['anthropic_version'] == 'vertex-2023-10-16'
assert 'service_tier' in body and 'container' in body and 'mcp_servers' in body and 'context_management' in body
print('Body ok:', list(body.keys()))
"
```

Pruebas end-to-end con credenciales reales (recomendadas antes de merge):

- **No-regresión Anthropic directo**: `InstantNeo(provider="anthropic", api_key=..., role_setup="...", model="...")` con un `.run("hola")` simple.
- **No-regresión Gemini directo**: equivalente con `provider="gemini"`.
- **Vertex Anthropic con params restaurados**: enviar una llamada con `service_tier="auto"` y verificar que el server no rechaza el body. Antes el parámetro se descartaba silenciosamente; ahora debería llegar al endpoint.
- **Vertex Anthropic streaming**: una llamada con `stream=True`. Antes el stream no funcionaba por el bug mencionado.
- **Vertex Gemini básico**: `InstantNeo(provider="vertexai", location="us-central1", service_account_file=..., role_setup="...", model="gemini-2.0-flash")`.
- **Vertex Gemini streaming**: confirmar que `?alt=sse` funciona contra el endpoint Vertex. Si en algún caso no fuera así, el fix está localizado: sobrescribir `generate_content_stream` en `VertexGeminiClient` con un parser line-buffered (el código original que se borró tenía esa variante; está en el historial git si se necesita rescatar).

Riesgo conocido pendiente de validación contra el endpoint real: el formato de SSE de Vertex Gemini con `?alt=sse`. La hipótesis del refactor es que Vertex acepta el mismo formato que Gemini directo; el parser heredado de `GeminiClient` debería funcionar.
