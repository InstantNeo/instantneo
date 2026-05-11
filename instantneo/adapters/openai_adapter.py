"""
Adapter para OpenAI API (endpoint /v1/responses).

Traduce entre el formato estándar de InstantNeo y el formato de OpenAI,
utilizando el fetcher HTTP puro en lugar del SDK.

Diferencias clave del endpoint /v1/responses:
- Usa 'input' en lugar de 'messages'
- Usa 'instructions' para el system message
- Usa 'max_output_tokens' en lugar de 'max_tokens'
- La respuesta tiene 'output' en lugar de 'choices'
- Las tools usan formato diferente
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
from instantneo.fetchers.openai import (
    OpenAIClient,
    InputMessage,
    FunctionTool,
)
from instantneo.models.openai import ReasoningConfig


class OpenAIAdapter(BaseAdapter):
    """
    Adapter para OpenAI API (endpoint /v1/responses).

    OpenAI Responses API tiene diferencias con Chat Completions:
    - input en lugar de messages
    - instructions como parámetro separado para system
    - max_output_tokens en lugar de max_tokens
    - output[] en lugar de choices[]
    """

    def __init__(self, api_key: str):
        """
        Inicializa el adapter con el cliente HTTP.

        Args:
            api_key: API key de OpenAI
        """
        self.client = OpenAIClient(api_key=api_key)

    def complete(self, request: StandardRequest) -> StandardResponse:
        """
        Ejecuta una completion usando OpenAI API.

        Args:
            request: Petición en formato estándar

        Returns:
            StandardResponse con la respuesta del modelo
        """
        try:
            # Extraer instructions (system) y mensajes
            instructions, openai_input = self._extract_instructions_and_input(request.messages)

            # Traducir tools
            openai_tools = self._translate_tools(request.tools) if request.tools else None
            openai_tool_choice = self._translate_tool_choice(request.tool_choice) if request.tool_choice else None

            # Construir parámetros extra
            extra_params = dict(request.provider_params)
            if request.reasoning:
                self._warn_unsupported_reasoning_keys(request.reasoning, {"effort", "summary"})
                extra_params["reasoning"] = ReasoningConfig(
                    effort=request.reasoning.get("effort", "medium"),
                    summary=request.reasoning.get("summary"),
                )

            # Llamar al fetcher
            response = self.client.create_completion(
                model=request.model,
                input=openai_input,
                instructions=instructions,
                max_output_tokens=request.max_tokens,
                temperature=request.temperature,
                tools=openai_tools,
                tool_choice=openai_tool_choice,
                stream=False,
                **extra_params,
            )

            # Traducir respuesta OpenAI → formato estándar
            return self._translate_response(response)

        except Exception as e:
            raise RuntimeError(f"Error en OpenAI API: {str(e)}")

    def complete_stream(self, request: StandardRequest) -> Iterator[StandardStreamChunk]:
        """
        Ejecuta una completion con streaming usando OpenAI API.

        Args:
            request: Petición en formato estándar

        Yields:
            StandardStreamChunk con fragmentos de la respuesta
        """
        try:
            # Extraer instructions (system) y mensajes
            instructions, openai_input = self._extract_instructions_and_input(request.messages)

            # Traducir tools
            openai_tools = self._translate_tools(request.tools) if request.tools else None
            openai_tool_choice = self._translate_tool_choice(request.tool_choice) if request.tool_choice else None

            # Construir parámetros extra
            extra_params = dict(request.provider_params)
            if request.reasoning:
                self._warn_unsupported_reasoning_keys(request.reasoning, {"effort", "summary"})
                extra_params["reasoning"] = ReasoningConfig(
                    effort=request.reasoning.get("effort", "medium"),
                    summary=request.reasoning.get("summary"),
                )

            # Llamar al fetcher con streaming
            stream = self.client.create_completion_stream(
                model=request.model,
                input=openai_input,
                instructions=instructions,
                max_output_tokens=request.max_tokens,
                temperature=request.temperature,
                tools=openai_tools,
                tool_choice=openai_tool_choice,
                **extra_params,
            )

            # Traducir chunks
            for chunk in stream:
                translated = self._translate_stream_chunk(chunk)
                if translated:
                    yield translated

        except Exception as e:
            raise RuntimeError(f"Error en OpenAI API streaming: {str(e)}")

    def supports_images(self) -> bool:
        """OpenAI soporta imágenes con GPT-4 Vision y modelos posteriores."""
        return True

    # =========================================================================
    # MÉTODOS DE TRADUCCIÓN: StandardRequest → OpenAI
    # =========================================================================

    def _extract_instructions_and_input(self, messages: List) -> tuple:
        """
        Extrae instructions (system) y convierte mensajes al formato OpenAI.

        OpenAI Responses API usa 'instructions' para system y 'input' para mensajes.

        Returns:
            Tuple de (instructions, list_of_input_items)
        """
        instructions = None
        openai_input = []

        for msg in messages:
            if msg.role == "system":
                # Acumular contenido de instructions
                if instructions is None:
                    instructions = msg.content if isinstance(msg.content, str) else ""
                else:
                    instructions += "\n" + (msg.content if isinstance(msg.content, str) else "")
            else:
                # Convertir mensaje normal
                content = msg.content
                if isinstance(content, list):
                    content = self._translate_content_blocks(content)

                # OpenAI usa InputMessage o dict
                openai_msg = {
                    "role": msg.role if msg.role != "tool" else "tool",
                    "content": content,
                }

                # Agregar campos opcionales
                if msg.name:
                    openai_msg["name"] = msg.name
                if msg.tool_call_id:
                    openai_msg["tool_call_id"] = msg.tool_call_id
                if msg.tool_calls:
                    openai_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ]

                openai_input.append(openai_msg)

        return instructions, openai_input

    def _translate_content_blocks(self, blocks: List) -> List[Dict[str, Any]]:
        """Traduce content blocks al formato OpenAI /v1/responses."""
        result = []

        for block in blocks:
            if hasattr(block, 'type'):
                # Formato estándar con objetos
                if block.type == "text":
                    result.append({
                        "type": "input_text",
                        "text": block.text,
                    })
                elif block.type == "image":
                    image_block = {
                        "type": "input_image",
                        "detail": block.detail or "auto",
                    }
                    if block.url:
                        image_block["image_url"] = block.url
                    elif block.base64 and block.media_type:
                        image_block["image_url"] = f"data:{block.media_type};base64,{block.base64}"
                    result.append(image_block)

            elif isinstance(block, dict):
                block_type = block.get("type", "")

                if block_type == "text":
                    result.append({
                        "type": "input_text",
                        "text": block.get("text", ""),
                    })
                elif block_type == "image_url":
                    # Formato legacy de OpenAI Chat Completions → convertir a /v1/responses
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
                                "type": "input_image",
                                "image_url": f"data:{media_type};base64,{base64_data}",
                            })
                    else:
                        # Es URL directa
                        result.append({
                            "type": "input_image",
                            "image_url": url,
                        })
                elif block_type in ("input_text", "input_image", "image"):
                    # Ya está en formato compatible
                    result.append(block)
                else:
                    # Pasar directo otros formatos
                    result.append(block)

        return result

    def _translate_tools(self, tools: List) -> List[Dict[str, Any]]:
        """Traduce herramientas estándar al formato OpenAI /v1/responses."""
        # OpenAI /v1/responses usa formato plano: {"type": "function", "name": ..., ...}
        result = []
        for tool in tools:
            params = tool.parameters if tool.parameters else {"type": "object", "properties": {}}

            result.append({
                "type": "function",
                "name": tool.name,
                "description": tool.description or "",
                "parameters": params,
                # strict=False por defecto - strict mode requiere ALL params en required
            })
        return result

    def _translate_tool_choice(self, tool_choice) -> Any:
        """Traduce tool_choice estándar al formato OpenAI."""
        if tool_choice.type == "auto":
            return "auto"
        elif tool_choice.type == "none":
            return "none"
        elif tool_choice.type == "required":
            return "required"
        elif tool_choice.type == "specific" and tool_choice.name:
            return {
                "type": "function",
                "name": tool_choice.name,
            }
        return "auto"

    # =========================================================================
    # MÉTODOS DE TRADUCCIÓN: OpenAI → StandardResponse
    # =========================================================================

    def _translate_response(self, response) -> StandardResponse:
        """Traduce respuesta OpenAI al formato estándar."""
        # Extraer contenido de texto, reasoning y tool_calls del output
        text_content = ""
        reasoning_content = ""
        tool_calls = []

        if response.output:
            for item in response.output:
                # Obtener tipo de forma segura (objeto o dict)
                item_type = getattr(item, 'type', None) or (item.get('type') if isinstance(item, dict) else None)

                if item_type == "message":
                    # Mensaje con contenido - obtener content de forma segura
                    item_content = getattr(item, 'content', None) or (item.get('content') if isinstance(item, dict) else None)
                    if item_content:
                        for content_block in item_content:
                            # Obtener tipo de content_block de forma segura
                            block_type = getattr(content_block, 'type', None) or (content_block.get('type') if isinstance(content_block, dict) else None)
                            if block_type == "output_text":
                                block_text = getattr(content_block, 'text', None) or (content_block.get('text') if isinstance(content_block, dict) else None)
                                text_content += block_text or ""
                elif item_type == "reasoning":
                    # Reasoning block — extract summary text
                    summary = getattr(item, 'summary', None) or (item.get('summary') if isinstance(item, dict) else None)
                    content_val = getattr(item, 'content', None) or (item.get('content') if isinstance(item, dict) else None)
                    if summary:
                        for s in summary:
                            text = getattr(s, 'text', None) or (s.get('text') if isinstance(s, dict) else None)
                            if text:
                                reasoning_content += text
                    elif content_val:
                        reasoning_content += str(content_val)
                elif item_type == "function_call":
                    # Tool call - obtener campos de forma segura
                    call_id = getattr(item, 'call_id', None) or (item.get('call_id') if isinstance(item, dict) else None)
                    item_id = getattr(item, 'id', None) or (item.get('id') if isinstance(item, dict) else None)
                    item_name = getattr(item, 'name', None) or (item.get('name') if isinstance(item, dict) else None)
                    item_args = getattr(item, 'arguments', None) or (item.get('arguments') if isinstance(item, dict) else None)

                    tool_calls.append(StandardToolCall(
                        id=call_id or item_id or "",
                        name=item_name,
                        arguments=item_args if isinstance(item_args, str) else json.dumps(item_args) if item_args else "{}",
                    ))

        # También revisar output_text directo
        if response.output_text:
            text_content = response.output_text

        # Construir mensaje de respuesta
        response_message = StandardResponseMessage(
            content=text_content if text_content else None,
            tool_calls=tool_calls if tool_calls else None,
            reasoning=reasoning_content if reasoning_content else None,
        )

        # Construir choice estándar
        standard_choice = StandardChoice(
            message=response_message,
            finish_reason=self._translate_status(response.status),
            index=0,
        )

        # Traducir usage (OpenAI usa prompt_tokens y completion_tokens).
        # reasoning_tokens viene en output_tokens_details.reasoning_tokens
        # (Responses API) o completion_tokens_details.reasoning_tokens
        # (Chat Completions API) según versión del SDK — probamos ambos.
        reasoning_tokens = None
        if response.usage:
            output_details = getattr(response.usage, 'output_tokens_details', None)
            completion_details = getattr(response.usage, 'completion_tokens_details', None)
            if output_details is not None:
                reasoning_tokens = getattr(output_details, 'reasoning_tokens', None)
            if reasoning_tokens is None and completion_details is not None:
                reasoning_tokens = getattr(completion_details, 'reasoning_tokens', None)

        usage = StandardUsage(
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
            reasoning_tokens=reasoning_tokens,
        )

        return StandardResponse(
            id=response.id,
            model=response.model,
            choices=[standard_choice],
            usage=usage,
            finish_reason=self._translate_status(response.status),
            raw_response=response,
        )

    def _translate_status(self, status: Optional[str]) -> str:
        """Traduce status de OpenAI al formato estándar finish_reason."""
        mapping = {
            "completed": "stop",
            "incomplete": "length",
            "cancelled": "stop",
            "failed": "error",
            "in_progress": "null",
        }
        return mapping.get(status, status or "unknown")

    def _translate_stream_chunk(self, chunk: Dict[str, Any]) -> Optional[StandardStreamChunk]:
        """Traduce un chunk de streaming OpenAI al formato estándar."""
        delta = StandardStreamDelta()
        event_type = chunk.get("type", "")

        # Procesar diferentes tipos de eventos de OpenAI Responses API
        if event_type == "response.reasoning_text.delta":
            delta.reasoning = chunk.get("delta", "")

        elif event_type == "response.output_text.delta":
            delta.content = chunk.get("delta", "")

        elif event_type == "response.function_call_arguments.delta":
            delta.tool_calls = [{
                "id": chunk.get("call_id", ""),
                "arguments_delta": chunk.get("delta", ""),
            }]

        elif event_type == "response.completed":
            delta.finish_reason = "stop"

        elif event_type == "response.failed":
            delta.finish_reason = "error"

        elif event_type in ("response.created", "response.in_progress"):
            # Eventos iniciales, extraer info básica
            response_data = chunk.get("response", {})
            return StandardStreamChunk(
                id=response_data.get("id", chunk.get("id", "")),
                model=response_data.get("model", chunk.get("model", "")),
                delta=delta,
                usage=None,
            )

        elif event_type in ("rate_limits.updated",):
            # Eventos que podemos ignorar
            return None

        # Extraer usage si está presente
        usage = None
        if "usage" in chunk:
            usage_data = chunk["usage"]
            output_details = usage_data.get("output_tokens_details") or {}
            usage = StandardUsage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                reasoning_tokens=output_details.get("reasoning_tokens"),
            )

        # Si no hay contenido relevante, retornar None
        if delta.content is None and delta.tool_calls is None and delta.reasoning is None and delta.finish_reason is None:
            return None

        return StandardStreamChunk(
            id=chunk.get("response_id", chunk.get("id", "")),
            model=chunk.get("model", ""),
            delta=delta,
            usage=usage,
        )
