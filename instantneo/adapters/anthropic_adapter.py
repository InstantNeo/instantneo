"""
Adapter para Anthropic Claude API.

Traduce entre el formato estándar de InstantNeo y el formato de Anthropic,
utilizando el fetcher HTTP puro en lugar del SDK.

Diferencias clave de Anthropic:
- El mensaje system es un parámetro separado (no va en messages)
- max_tokens es REQUERIDO
- Las tools usan input_schema en lugar de parameters
- tool_choice usa formato objeto {type: "auto"|"any"|"tool"|"none"}
- La respuesta tiene content[] en lugar de choices[]
"""

from typing import Iterator, Dict, Any, List, Optional
import json

from instantneo.adapters.base_adapter import BaseAdapter
from instantneo.models.standard import (
    StandardRequest,
    StandardResponse,
    StandardChoice,
    StandardResponseMessage,
    StandardUsage,
    StandardToolCall,
    StandardStreamChunk,
    StandardStreamDelta,
)
from instantneo.fetchers.anthropic import (
    AnthropicClient,
    Message as AnthropicMessage,
    Tool as AnthropicTool,
)


class AnthropicAdapter(BaseAdapter):
    """
    Adapter para Anthropic Claude API.

    Anthropic tiene un formato diferente a OpenAI:
    - system es parámetro de nivel superior, no un mensaje
    - max_tokens es obligatorio
    - tools usan input_schema en lugar de parameters
    - tool_choice es objeto, no string
    - response.content[] en lugar de response.choices[]
    """

    # Valor por defecto para max_tokens si no se especifica
    DEFAULT_MAX_TOKENS = 4096

    def __init__(self, api_key: str):
        """
        Inicializa el adapter con el cliente HTTP.

        Args:
            api_key: API key de Anthropic
        """
        self.client = AnthropicClient(api_key=api_key)

    def complete(self, request: StandardRequest) -> StandardResponse:
        """
        Ejecuta una completion usando Anthropic API.

        Args:
            request: Petición en formato estándar

        Returns:
            StandardResponse con la respuesta del modelo
        """
        try:
            # Extraer system message y mensajes normales
            system_content, anthropic_messages = self._extract_system_and_messages(request.messages)

            # Traducir tools
            anthropic_tools = self._translate_tools(request.tools) if request.tools else None
            anthropic_tool_choice = self._translate_tool_choice(request.tool_choice) if request.tool_choice else None

            # max_tokens es requerido en Anthropic
            max_tokens = request.max_tokens or self.DEFAULT_MAX_TOKENS

            # Construir parámetros extra
            extra_params = dict(request.provider_params)
            if request.reasoning:
                self._warn_unsupported_reasoning_keys(request.reasoning, {"effort", "budget_tokens"})
                budget = request.reasoning.get("budget_tokens")
                if not budget:
                    effort_map = {"low": 1024, "medium": 4096, "high": 10240}
                    budget = effort_map.get(request.reasoning.get("effort", "medium"), 4096)
                extra_params["thinking"] = {"type": "enabled", "budget_tokens": budget}

            # Llamar al fetcher
            response = self.client.create_message(
                model=request.model,
                messages=anthropic_messages,
                max_tokens=max_tokens,
                system=system_content,
                temperature=request.temperature,
                top_p=request.top_p,
                stop_sequences=request.stop,
                tools=anthropic_tools,
                tool_choice=anthropic_tool_choice,
                stream=False,
                **extra_params,
            )

            # Traducir respuesta Anthropic → formato estándar
            return self._translate_response(response)

        except Exception as e:
            raise RuntimeError(f"Error en Anthropic API: {str(e)}")

    def complete_stream(self, request: StandardRequest) -> Iterator[StandardStreamChunk]:
        """
        Ejecuta una completion con streaming usando Anthropic API.

        Args:
            request: Petición en formato estándar

        Yields:
            StandardStreamChunk con fragmentos de la respuesta
        """
        try:
            # Extraer system message y mensajes normales
            system_content, anthropic_messages = self._extract_system_and_messages(request.messages)

            # Traducir tools
            anthropic_tools = self._translate_tools(request.tools) if request.tools else None
            anthropic_tool_choice = self._translate_tool_choice(request.tool_choice) if request.tool_choice else None

            # max_tokens es requerido en Anthropic
            max_tokens = request.max_tokens or self.DEFAULT_MAX_TOKENS

            # Construir parámetros extra
            extra_params = dict(request.provider_params)
            if request.reasoning:
                self._warn_unsupported_reasoning_keys(request.reasoning, {"effort", "budget_tokens"})
                budget = request.reasoning.get("budget_tokens")
                if not budget:
                    effort_map = {"low": 1024, "medium": 4096, "high": 10240}
                    budget = effort_map.get(request.reasoning.get("effort", "medium"), 4096)
                extra_params["thinking"] = {"type": "enabled", "budget_tokens": budget}

            # Llamar al fetcher con streaming
            stream = self.client.create_message_stream(
                model=request.model,
                messages=anthropic_messages,
                max_tokens=max_tokens,
                system=system_content,
                temperature=request.temperature,
                top_p=request.top_p,
                stop_sequences=request.stop,
                tools=anthropic_tools,
                tool_choice=anthropic_tool_choice,
                **extra_params,
            )

            # Traducir chunks
            for chunk in stream:
                translated = self._translate_stream_chunk(chunk)
                if translated:
                    yield translated

        except Exception as e:
            raise RuntimeError(f"Error en Anthropic API streaming: {str(e)}")

    def supports_images(self) -> bool:
        """Anthropic soporta imágenes desde Claude 3."""
        return True

    # =========================================================================
    # MÉTODOS DE TRADUCCIÓN: StandardRequest → Anthropic
    # =========================================================================

    def _extract_system_and_messages(self, messages: List) -> tuple:
        """
        Extrae el system message y convierte el resto al formato Anthropic.

        Anthropic requiere que system sea un parámetro separado, no un mensaje.

        Returns:
            Tuple de (system_content, list_of_messages)
        """
        system_content = None
        anthropic_messages = []

        for msg in messages:
            if msg.role == "system":
                # Acumular contenido de sistema
                if system_content is None:
                    system_content = msg.content if isinstance(msg.content, str) else ""
                else:
                    system_content += "\n" + (msg.content if isinstance(msg.content, str) else "")
            else:
                # Convertir mensaje normal
                content = msg.content
                if isinstance(content, list):
                    content = self._translate_content_blocks(content)
                elif msg.role == "tool":
                    # Anthropic usa tool_result como content block en mensajes user
                    content = [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": content if isinstance(content, str) else str(content),
                    }]

                anthropic_msg = AnthropicMessage(
                    role="user" if msg.role == "tool" else msg.role,
                    content=content,
                )
                anthropic_messages.append(anthropic_msg)

        return system_content, anthropic_messages

    def _translate_content_blocks(self, blocks: List) -> List[Dict[str, Any]]:
        """Traduce content blocks al formato Anthropic."""
        result = []

        for block in blocks:
            if hasattr(block, 'type'):
                # Formato estándar con objetos
                if block.type == "text":
                    result.append({
                        "type": "text",
                        "text": block.text,
                    })
                elif block.type == "image":
                    if block.base64 and block.media_type:
                        result.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": block.media_type,
                                "data": block.base64,
                            }
                        })
                    elif block.url:
                        result.append({
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": block.url,
                            }
                        })

            elif isinstance(block, dict):
                block_type = block.get("type", "")

                if block_type == "text":
                    result.append({
                        "type": "text",
                        "text": block.get("text", ""),
                    })
                elif block_type == "image_url":
                    # Formato legacy de OpenAI Chat Completions
                    image_data = block.get("image_url", {})
                    url = image_data.get("url", "") if isinstance(image_data, dict) else image_data

                    # Detectar si es base64 o URL
                    if url.startswith("data:"):
                        # Es base64: data:image/jpeg;base64,xxxx
                        parts = url.split(";base64,")
                        if len(parts) == 2:
                            media_type = parts[0].replace("data:", "")
                            base64_data = parts[1]
                            result.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64_data,
                                }
                            })
                    else:
                        # Es URL directa
                        result.append({
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": url,
                            }
                        })
                elif block_type == "image":
                    # Ya está en formato Anthropic
                    result.append(block)
                else:
                    # Pasar directo otros formatos
                    result.append(block)

        return result

    def _translate_tools(self, tools: List) -> List[AnthropicTool]:
        """Traduce herramientas estándar al formato Anthropic."""
        return [
            AnthropicTool(
                name=tool.name,
                description=tool.description,
                input_schema=tool.parameters,  # Anthropic usa input_schema
            )
            for tool in tools
        ]

    def _translate_tool_choice(self, tool_choice) -> Dict[str, Any]:
        """Traduce tool_choice estándar al formato Anthropic."""
        if tool_choice.type == "auto":
            return {"type": "auto"}
        elif tool_choice.type == "none":
            return {"type": "none"}
        elif tool_choice.type == "required":
            return {"type": "any"}  # Anthropic usa "any" para required
        elif tool_choice.type == "specific" and tool_choice.name:
            return {"type": "tool", "name": tool_choice.name}
        return {"type": "auto"}

    # =========================================================================
    # MÉTODOS DE TRADUCCIÓN: Anthropic → StandardResponse
    # =========================================================================

    def _translate_response(self, response) -> StandardResponse:
        """Traduce respuesta Anthropic al formato estándar."""
        # Extraer contenido de texto, reasoning y tool_calls
        text_content = ""
        reasoning_content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "thinking":
                reasoning_content += getattr(block, 'thinking', '') or ''
            elif block.type == "text":
                text_content += block.text or ""
            elif block.type == "tool_use":
                # Convertir tool_use a StandardToolCall
                tool_calls.append(StandardToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=json.dumps(block.input) if isinstance(block.input, dict) else str(block.input),
                ))

        # Construir mensaje de respuesta
        response_message = StandardResponseMessage(
            content=text_content if text_content else None,
            tool_calls=tool_calls if tool_calls else None,
            reasoning=reasoning_content if reasoning_content else None,
        )

        # Construir choice estándar (Anthropic no tiene choices, simulamos uno)
        standard_choice = StandardChoice(
            message=response_message,
            finish_reason=self._translate_stop_reason(response.stop_reason),
            index=0,
        )

        return StandardResponse(
            id=response.id,
            model=response.model,
            choices=[standard_choice],
            usage=StandardUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            ),
            finish_reason=self._translate_stop_reason(response.stop_reason),
            raw_response=response,
        )

    def _translate_stop_reason(self, stop_reason: Optional[str]) -> str:
        """Traduce stop_reason de Anthropic al formato estándar."""
        mapping = {
            "end_turn": "stop",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
        }
        return mapping.get(stop_reason, stop_reason or "unknown")

    def _translate_stream_chunk(self, chunk: Dict[str, Any]) -> Optional[StandardStreamChunk]:
        """Traduce un chunk de streaming Anthropic al formato estándar."""
        event_type = chunk.get("type", "")
        delta = StandardStreamDelta()

        # Procesar diferentes tipos de eventos de Anthropic
        if event_type == "content_block_delta":
            delta_data = chunk.get("delta", {})
            if delta_data.get("type") == "thinking_delta":
                delta.reasoning = delta_data.get("thinking")
            elif delta_data.get("type") == "text_delta":
                delta.content = delta_data.get("text")
            elif delta_data.get("type") == "input_json_delta":
                # Tool call arguments
                delta.tool_calls = [{"partial_json": delta_data.get("partial_json")}]

        elif event_type == "message_delta":
            delta_data = chunk.get("delta", {})
            delta.finish_reason = self._translate_stop_reason(delta_data.get("stop_reason"))

        elif event_type == "message_start":
            # Mensaje inicial, extraer info del mensaje
            message = chunk.get("message", {})
            return StandardStreamChunk(
                id=message.get("id", ""),
                model=message.get("model", ""),
                delta=delta,
                usage=None,
            )

        elif event_type == "message_stop":
            # Mensaje final
            delta.finish_reason = "stop"

        elif event_type in ("ping", "content_block_start", "content_block_stop"):
            # Eventos que podemos ignorar o no necesitan traducción especial
            return None

        # Extraer usage si está presente
        usage = None
        if "usage" in chunk:
            usage_data = chunk["usage"]
            usage = StandardUsage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
            )

        # Si no hay contenido relevante, retornar None
        if delta.content is None and delta.tool_calls is None and delta.reasoning is None and delta.finish_reason is None:
            return None

        return StandardStreamChunk(
            id=chunk.get("id", "") or chunk.get("message", {}).get("id", ""),
            model=chunk.get("model", "") or chunk.get("message", {}).get("model", ""),
            delta=delta,
            usage=usage,
        )
