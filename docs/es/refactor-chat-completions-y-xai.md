# Refactor: ChatCompletionsAdapter base + xAI directo + xAI en Vertex Model Garden

## Resumen ejecutivo

Se introduce una capa base reutilizable (`ChatCompletionsClient` + `ChatCompletionsAdapter`) para todos los providers que usan el formato OpenAI chat/completions clásico. `GroqAdapter` se refactoriza para heredar de esa base, y se añaden tres providers nuevos: **xAI directo** (`api.x.ai`), **Vertex xAI** (Model Garden) y, gratis para el futuro, cualquier provider OpenAI-compat (Mistral, DeepSeek, Together, Fireworks, Llama, Perplexity) que se quiera añadir en ~25 líneas.

La API pública de `InstantNeo(...)` no cambia para los providers existentes. Se añaden dos nuevos: `provider="xai"` y `provider="vertex_xai"`.

## Motivación

1. **Integrar xAI** es un requerimiento concreto. Sin la abstracción, el camino más corto sería duplicar todo el cliente HTTP y todo el adapter — exactamente la misma deuda que se acaba de eliminar para Anthropic/Gemini en Vertex.

2. **El parche externo de xAI no funciona**. El parche que existe en `instantneo_patch/` importa `_create_jwt`, `_exchange_jwt_for_token`, `_load_service_account` desde `instantneo.fetchers.vertexai`, módulo que se borró en el refactor anterior (ahora vive en `instantneo.fetchers.vertex._auth`). Además sigue el patrón viejo de copy-paste: `vertex_xai.py` reimplementa el cliente HTTP entero en lugar de heredar.

3. **El formato chat/completions clásico es el estándar de facto** para inferencia de terceros. Lo usan al menos 10 providers: Groq, xAI, Mistral, DeepSeek, Together AI, Fireworks, Perplexity, Cohere, OpenRouter, y dentro de Vertex también xAI/Mistral/Llama vía el endpoint `endpoints/openapi/chat/completions`. Es razonable invertir una vez en la abstracción.

4. **`GroqAdapter` (354 líneas) es ~95% lógica chat/completions genérica.** Solo unas pocas líneas son Groq-específicas (validaciones de límites, campo `reasoning_format`). Mover lo genérico a una base no cambia comportamiento de Groq, y habilita a los demás providers.

## Decisión arquitectónica

### Tres capas, dos ejes ortogonales

```
                  ┌─────────────────────────────────────┐
                  │  StandardRequest / StandardResponse │  ← contrato InstantNeo
                  └─────────────────────────────────────┘
                                   ↑
        ┌──────────────────────────┴──────────────────────────┐
        │                                                     │
   ChatCompletionsAdapter (base)                  Otros adapters por shape
   ╔════════════════════════════╗                 (AnthropicAdapter, GeminiAdapter,
   ║ traducción genérica         ║                 OpenAIAdapter — APIs distintas)
   ║ chat/completions ↔ Standard ║
   ╚════════════════════════════╝
        ↑           ↑           ↑
   GroqAdapter  XAIAdapter  VertexXAIAdapter
                              (hereda XAIAdapter, swap cliente)


   ChatCompletionsClient (base, mecánica HTTP genérica)
        ↑           ↑                  ↑
   GroqClient  XAIClient            VertexXAIClient
                                    (Mixin VertexAuth + XAIClient)
```

### Vertex Model Garden vs per-publisher

Se descubrió investigando docs oficiales que **Vertex AI tiene tres categorías de modelos**, no dos:

- **Google Models** (first-party): Gemini, Imagen, Veo, Lyria.
- **Partner Models**: Anthropic Claude, Mistral, **xAI Grok**.
- **Open Models**: Llama.

"Model Garden" es el hub de descubrimiento, no una categoría. Por eso Anthropic, xAI, Mistral y Llama están todos "en Model Garden". La distinción real para el código es **qué shape de API usa cada uno**:

| Hosting | Endpoint | Shape body |
|---|---|---|
| Gemini en Vertex | `publishers/google/models/{model}:generateContent` | Gemini contents API |
| **Anthropic Claude en Vertex (excepción)** | `publishers/anthropic/models/{model}:rawPredict` | Anthropic Messages API nativa |
| **xAI / Mistral / Llama en Vertex** | `endpoints/openapi/chat/completions` | **OpenAI chat/completions** |

Anthropic es la excepción entre los partners — mantiene su shape nativa. Los demás partners y todos los open models comparten el endpoint OpenAI-compat unificado donde **el modelo va en el body con prefijo** (`xai/grok-...`, `meta/llama-...`).

Por eso `VertexAuthMixin` ahora expone **dos** helpers de endpoint:
- `_vertex_endpoint(publisher, model, action)` — para per-publisher (Anthropic, Gemini).
- `_vertex_openai_compat_endpoint()` — para Model Garden (xAI, Mistral, Llama).

## Patrón unificado para futuros providers OpenAI-compat

Receta concreta para añadir cualquier provider OpenAI-compat (ej. Mistral directo + Mistral en Vertex):

**1. Fetcher directo** — crear `instantneo/fetchers/mistral.py`:

```python
from instantneo.fetchers._chat_completions import ChatCompletionsClient

class MistralClient(ChatCompletionsClient):
    BASE_URL = "https://api.mistral.ai/v1/chat/completions"
```

**2. Adapter directo** — crear `instantneo/adapters/mistral_adapter.py`:

```python
from instantneo.adapters._chat_completions import ChatCompletionsAdapter
from instantneo.fetchers.mistral import MistralClient

class MistralAdapter(ChatCompletionsAdapter):
    def __init__(self, api_key: str):
        self.client = MistralClient(api_key=api_key)

    def get_provider_name(self) -> str:
        return "mistral"
```

**3. Fetcher Vertex** — crear `instantneo/fetchers/vertex/mistral.py`:

```python
from instantneo.fetchers.mistral import MistralClient
from instantneo.fetchers.vertex._auth import VertexAuthMixin

class VertexMistralClient(VertexAuthMixin, MistralClient):
    PUBLISHER_PREFIX = "mistralai/"

    def __init__(self, location, ...):
        VertexAuthMixin.__init__(self, location=location, ...)

    def _build_headers(self):
        return self._build_vertex_headers()

    def _get_url(self, model, stream=False):
        return self._vertex_openai_compat_endpoint()

    def _build_request_body(self, messages, model, **kwargs):
        if not model.startswith(self.PUBLISHER_PREFIX):
            model = f"{self.PUBLISHER_PREFIX}{model}"
        return super()._build_request_body(messages=messages, model=model, **kwargs)
```

**4. Adapter Vertex** — crear `instantneo/adapters/vertex_mistral_adapter.py`:

```python
from instantneo.adapters.mistral_adapter import MistralAdapter
from instantneo.fetchers.vertex.mistral import VertexMistralClient

class VertexMistralAdapter(MistralAdapter):
    def __init__(self, location, ...):
        self.client = VertexMistralClient(location=location, ...)

    def get_provider_name(self) -> str:
        return "vertex_mistral"
```

**5. Registro** en `core.py:adapter_map`:

```python
"mistral": ("instantneo.adapters.mistral_adapter", "MistralAdapter"),
"vertex_mistral": ("instantneo.adapters.vertex_mistral_adapter", "VertexMistralAdapter"),
```

Total: ~70 líneas nuevas y se obtiene Mistral directo + Mistral en Vertex con tools, streaming SSE, imágenes, function calling y reasoning_tokens — todo heredado de la base.

## Cambios por archivo

| Archivo | Cambio | Motivo |
|---|---|---|
| `instantneo/models/_chat_completions.py` | Nuevo | Tipos del wire format chat/completions: `Message`, `Tool`, `ToolFunction`, `FunctionCall`, `ToolCall`, `ResponseMessage`, `Choice`, `Usage`, `ChatCompletionResponse`. Compartidos por todos los providers OpenAI-compat. |
| `instantneo/fetchers/_chat_completions.py` | Nuevo | `ChatCompletionsClient` base con mecánica HTTP genérica (headers Bearer, build body, parse response, parse stream SSE). Extrae lo que estaba duplicado en `groq.py`. |
| `instantneo/adapters/_chat_completions.py` | Nuevo | `ChatCompletionsAdapter` base con traducción genérica `StandardRequest ↔ chat/completions` (mensajes, content blocks con imágenes, tools, response, stream chunks). Lee `reasoning_tokens`. |
| `instantneo/fetchers/groq.py` | Refactor | `GroqClient` pasa de 600 líneas a ~120: hereda de `ChatCompletionsClient`, override `_validate_request` para límites Groq (max 128 tools, max 4 stop, n=1), override `_build_request_body` solo para `documents` y `search_settings` (extensiones Groq). Re-exporta tipos para compat. |
| `instantneo/adapters/groq_adapter.py` | Refactor | `GroqAdapter` pasa de 354 líneas a 15. Hereda de `ChatCompletionsAdapter` y solo declara cliente y nombre. |
| `instantneo/models/groq.py` | Refactor | Re-exporta tipos chat/completions desde `models/_chat_completions.py`. Mantiene `Document`, `SearchSettings`, `GroqError` (Groq-específicos). Compat de imports históricos garantizada. |
| `instantneo/fetchers/xai.py` | Nuevo | `XAIClient(ChatCompletionsClient)` con `BASE_URL = "https://api.x.ai/v1/chat/completions"`. ~50 líneas. |
| `instantneo/adapters/xai_adapter.py` | Nuevo | `XAIAdapter(ChatCompletionsAdapter)`, ~25 líneas. |
| `instantneo/fetchers/vertex/_auth.py` | Modificar | Añade `_vertex_openai_compat_endpoint()` y refactoriza `_vertex_endpoint` para reusar `_vertex_host()` común. |
| `instantneo/fetchers/vertex/xai.py` | Nuevo | `VertexXAIClient(VertexAuthMixin, XAIClient)`: override `_get_url` para Model Garden, override `_build_request_body` para añadir prefijo `xai/`. ~50 líneas. |
| `instantneo/adapters/vertex_xai_adapter.py` | Nuevo | `VertexXAIAdapter(XAIAdapter)`, paralelo a `vertex_anthropic_adapter` y `vertex_gemini_adapter`. ~30 líneas. |
| `instantneo/adapters/__init__.py` | Modificar | Añade try-imports de `XAIAdapter` y `VertexXAIAdapter`. |
| `instantneo/core.py` | Modificar | `adapter_map` añade `"xai"` y `"vertex_xai"`. La branch de auth Vertex (`if provider in ...`) incluye `"vertex_xai"`. |

**Borrar**: ninguno.

## Compatibilidad

**API pública intacta.** Cualquier código de usuario sigue funcionando sin cambios:

```python
InstantNeo(provider="groq", api_key="gsk_...", ...)             # idéntico
InstantNeo(provider="anthropic", api_key="sk-ant-...", ...)     # idéntico
InstantNeo(provider="gemini", api_key="AIza...", ...)           # idéntico
InstantNeo(provider="vertex_anthropic", location=..., ...)      # idéntico
InstantNeo(provider="vertexai", location=..., ...)              # idéntico
InstantNeo(provider="xai", api_key="xai-...", ...)              # NUEVO
InstantNeo(provider="vertex_xai", location=..., ...)            # NUEVO
```

**Imports históricos siguen funcionando**:

```python
from instantneo.models.groq import Message, Tool, GroqResponse    # OK (re-export)
from instantneo.models.groq import Document, SearchSettings       # OK (Groq-specific)
from instantneo.fetchers.groq import GroqClient, fetch_groq       # OK
from instantneo.adapters.groq_adapter import GroqAdapter          # OK
```

**Cambio interno relevante**: el `GroqResponse` actual es un alias de `ChatCompletionResponse`. Estructuralmente equivalente. Cualquier código que haga `isinstance(resp, GroqResponse)` sigue compilando.

## Convención de naming para clases base internas

Los archivos `_chat_completions.py` (en `models/`, `fetchers/` y `adapters/`) llevan prefijo `_` siguiendo la convención Python para "interno". No deben importarse directamente en código de usuario; los imports públicos viven en los archivos sin prefijo (`groq_adapter.py`, `xai_adapter.py`, etc.).

Las clases dentro (`ChatCompletionsClient`, `ChatCompletionsAdapter`) tienen además guards en `__init__` que hacen `raise TypeError` si se intenta instanciar la base directamente — para evitar accidentes.

## Cómo revisar el PR

Orden de lectura sugerido:

1. **`instantneo/models/_chat_completions.py`** — tipos del wire format. Es lo más simple; define los dataclasses y nada más.
2. **`instantneo/fetchers/_chat_completions.py`** — cliente HTTP base. Mecánica de POST + parse + SSE; los hooks `_get_url`, `_build_headers`, `_build_request_body`, `_parse_response`, `_validate_request` son sobrescribibles.
3. **`instantneo/fetchers/groq.py`** — confirmar que el refactor preserva comportamiento (validaciones Groq, extensiones `documents`/`search_settings`).
4. **`instantneo/adapters/_chat_completions.py`** — adapter base con traducción genérica. Lee `reasoning_tokens` desde el response.
5. **`instantneo/adapters/groq_adapter.py`** — el "antes 354 líneas, ahora 15". Verifica que no hace nada que la base no haga.
6. **`instantneo/fetchers/xai.py`** y **`adapters/xai_adapter.py`** — confirmar la simplicidad: solo BASE_URL y nombre.
7. **`instantneo/fetchers/vertex/_auth.py`** — el nuevo helper `_vertex_openai_compat_endpoint()`.
8. **`instantneo/fetchers/vertex/xai.py`** y **`adapters/vertex_xai_adapter.py`** — composición VertexAuthMixin + XAIClient + override de URL/prefijo modelo.
9. **`instantneo/core.py`** — entradas del `adapter_map` y branch de auth.

## Cómo verificar localmente

**Smoke tests automáticos** (`.test/smoke_vertex.py`):

```bash
cd .test
../.venv/bin/python smoke_vertex.py
```

Cubre 16 tests contra endpoints reales, distribuidos así:
- Vertex Anthropic: body con 4 params restaurados (estático), non-stream, streaming, tools.
- Vertex Gemini: non-stream, streaming, tools.
- **Groq directo**: non-stream, streaming, tools (no-regresión post-refactor).
- **xAI directo**: non-stream, streaming, tools.
- **Vertex xAI Model Garden**: non-stream, streaming, tools.

Requiere:
- Service account JSON en `.test/*.json`.
- Opcional `.test/config.py` con `GROQ_API_KEY` y `XAI_API_KEY`. Si faltan, los tests directos correspondientes se saltan.

Modelos verificados al momento de este PR (mayo 2026):
- Vertex Anthropic: `claude-haiku-4-5@20251001` en `us-east5`.
- Vertex Gemini: `gemini-3.1-flash-lite-preview` en `global`.
- Groq directo: `llama-3.3-70b-versatile`.
- xAI directo: `grok-4-fast-non-reasoning`.
- Vertex xAI: `grok-4.1-fast-reasoning` en `global` (con prefijo `xai/` añadido automáticamente por el cliente).

Resultado: **16/16 PASS**.

## Riesgos pendientes / decisiones documentadas

1. **xAI valida `reasoning_effort` con `low`/`high` (no `medium`).** Si código de usuario pasa `medium`, xAI devuelve 400. Es transparente — no se hace remapping silencioso. Documentado en el módulo del adapter.

2. **Groq exige `n=1`** y otros límites (max 128 tools, max 4 stop). El cliente Groq lo valida explícitamente; el comportamiento es idéntico al del repo previo al refactor.

3. **No se migró OpenAIAdapter** porque OpenAI usa `/v1/responses` (API distinta), no chat/completions. Sigue como adapter independiente.

4. **No se añadieron Mistral, Llama, DeepSeek, etc.** Solo se establecieron los hooks. La incorporación se hace cuando se necesite, en ~70 líneas por provider (directo + Vertex), siguiendo la receta arriba.
