"""
Adapter para Cerebras API.

Traduce entre el formato estándar de InstantNeo y el formato de Cerebras,
utilizando el fetcher HTTP puro en lugar del SDK.
"""

from typing import Iterator, Dict, Any, List
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
from instantneo.fetchers.cerebras import CerebrasClient, Message, Tool, ToolFunction


class CerebrasAdapter(BaseAdapter):
    """
    Adapter para Cerebras API.

    Cerebras usa un formato compatible con OpenAI Chat Completions, lo que simplifica
    la traducción. Las principales diferencias son:
    - max_tokens → max_completion_tokens
    - temperature rango 0-1.5
    - Soporte para clear_thinking y reasoning
    - time_info en la respuesta con tiempos de procesamiento
    - Soporte para speculative decoding via prediction
    """

    def __init__(self, api_key: str):
        """
        Inicializa el adapter con el cliente HTTP.

        Args:
            api_key: API key de Cerebras
        """
        self.client = CerebrasClient(api_key=api_key)

    def complete(self, request: StandardRequest) -> StandardResponse:
        """
        Ejecuta una completion usando Cerebras API.

        Args:
            request: Petición en formato estándar

        Returns:
            StandardResponse con la respuesta del modelo
        """
        try:
            # Traducir request estándar → formato Cerebras
            cerebras_messages = self._translate_messages(request.messages)
            cerebras_tools = self._translate_tools(request.tools) if request.tools else None
            cerebras_tool_choice = self._translate_tool_choice(request.tool_choice) if request.tool_choice else None

            # Construir parámetros extra
            extra_params = dict(request.provider_params)
            if request.reasoning:
                self._warn_unsupported_reasoning_keys(request.reasoning, {"effort"})
                extra_params["reasoning_effort"] = request.reasoning.get("effort", "medium")

            # Llamar al fetcher
            response = self.client.create_chat_completion(
                messages=cerebras_messages,
                model=request.model,
                temperature=request.temperature,
                max_completion_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=request.stop,
                seed=request.seed,
                tools=cerebras_tools,
                tool_choice=cerebras_tool_choice,
                stream=False,
                **extra_params,
            )

            # Traducir respuesta Cerebras → formato estándar
            return self._translate_response(response)

        except Exception as e:
            raise RuntimeError(f"Error en Cerebras API: {e}") from e

    def complete_stream(self, request: StandardRequest) -> Iterator[StandardStreamChunk]:
        """
        Ejecuta una completion con streaming usando Cerebras API.

        Args:
            request: Petición en formato estándar

        Yields:
            StandardStreamChunk con fragmentos de la respuesta
        """
        try:
            # Traducir request
            cerebras_messages = self._translate_messages(request.messages)
            cerebras_tools = self._translate_tools(request.tools) if request.tools else None
            cerebras_tool_choice = self._translate_tool_choice(request.tool_choice) if request.tool_choice else None

            # Construir parámetros extra
            extra_params = dict(request.provider_params)
            if request.reasoning:
                self._warn_unsupported_reasoning_keys(request.reasoning, {"effort"})
                extra_params["reasoning_effort"] = request.reasoning.get("effort", "medium")

            # Llamar al fetcher con streaming
            stream = self.client.create_chat_completion_stream(
                messages=cerebras_messages,
                model=request.model,
                temperature=request.temperature,
                max_completion_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=request.stop,
                seed=request.seed,
                tools=cerebras_tools,
                tool_choice=cerebras_tool_choice,
                **extra_params,
            )

            # Traducir chunks
            for chunk in stream:
                yield self._translate_stream_chunk(chunk)

        except Exception as e:
            raise RuntimeError(f"Error en Cerebras API streaming: {e}") from e

    def supports_images(self) -> bool:
        """Cerebras soporta imágenes con modelos de visión."""
        return True

    # =========================================================================
    # MÉTODOS DE TRADUCCIÓN: StandardRequest → Cerebras
    # =========================================================================

    def _translate_messages(self, messages: List) -> List[Message]:
        """Traduce mensajes estándar al formato Cerebras."""
        cerebras_messages = []

        for msg in messages:
            # Manejar contenido (puede ser string o lista de content blocks)
            content = msg.content
            if isinstance(content, list):
                # Convertir content blocks al formato Cerebras
                content = self._translate_content_blocks(content)

            cerebras_msg = Message(
                role=msg.role,
                content=content,
                name=msg.name,
                tool_call_id=msg.tool_call_id,
            )

            # Agregar tool_calls si existen (para mensajes de assistant)
            if msg.tool_calls:
                cerebras_msg.tool_calls = [
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

            cerebras_messages.append(cerebras_msg)

        return cerebras_messages

    def _translate_content_blocks(self, blocks: List) -> List[Dict[str, Any]]:
        """Traduce content blocks al formato Cerebras (compatible OpenAI Chat Completions)."""
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
                    if block.url:
                        url = block.url
                    elif block.base64 and block.media_type:
                        url = f"data:{block.media_type};base64,{block.base64}"
                    else:
                        continue
                    result.append({
                        "type": "image_url",
                        "image_url": {"url": url},
                    })

            elif isinstance(block, dict):
                block_type = block.get("type", "")

                if block_type == "text":
                    result.append({
                        "type": "text",
                        "text": block.get("text", ""),
                    })
                elif block_type == "image_url":
                    # Ya está en formato Cerebras/OpenAI
                    result.append(block)
                elif block_type == "image":
                    # Convertir formato estándar a image_url
                    source = block.get("source", {})
                    if source.get("type") == "url":
                        result.append({
                            "type": "image_url",
                            "image_url": {"url": source.get("url", "")},
                        })
                    elif source.get("type") == "base64":
                        url = f"data:{source.get('media_type', '')};base64,{source.get('data', '')}"
                        result.append({
                            "type": "image_url",
                            "image_url": {"url": url},
                        })
                else:
                    # Pasar directo otros formatos
                    result.append(block)

        return result

    def _translate_tools(self, tools: List) -> List[Tool]:
        """Traduce herramientas estándar al formato Cerebras."""
        return [
            Tool(
                type="function",
                function=ToolFunction(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.parameters,
                )
            )
            for tool in tools
        ]

    def _translate_tool_choice(self, tool_choice) -> Any:
        """Traduce tool_choice estándar al formato Cerebras."""
        if tool_choice.type == "auto":
            return "auto"
        elif tool_choice.type == "none":
            return "none"
        elif tool_choice.type == "required":
            return "required"
        elif tool_choice.type == "specific" and tool_choice.name:
            return {
                "type": "function",
                "function": {"name": tool_choice.name}
            }
        return "auto"

    # =========================================================================
    # MÉTODOS DE TRADUCCIÓN: Cerebras → StandardResponse
    # =========================================================================

    def _translate_response(self, response) -> StandardResponse:
        """Traduce respuesta Cerebras al formato estándar."""
        # Obtener el primer choice
        choice = response.choices[0] if response.choices else None

        if not choice:
            return StandardResponse(
                id=response.id,
                model=response.model,
                choices=[],
                usage=StandardUsage(
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                    reasoning_tokens=getattr(
                        getattr(response.usage, 'completion_tokens_details', None),
                        'reasoning_tokens', None,
                    ),
                ),
                finish_reason="error",
                raw_response=response,
            )

        # Traducir tool_calls si existen
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                StandardToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in choice.message.tool_calls
            ]

        content = choice.message.content
        reasoning_content = choice.message.reasoning if choice.message.reasoning else None

        # Construir mensaje de respuesta
        response_message = StandardResponseMessage(
            content=content,
            tool_calls=tool_calls,
            reasoning=reasoning_content,
        )

        # Construir choice estándar
        standard_choice = StandardChoice(
            message=response_message,
            finish_reason=choice.finish_reason,
            index=choice.index,
        )

        return StandardResponse(
            id=response.id,
            model=response.model,
            choices=[standard_choice],
            usage=StandardUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                reasoning_tokens=getattr(
                    getattr(response.usage, 'completion_tokens_details', None),
                    'reasoning_tokens', None,
                ),
            ),
            finish_reason=choice.finish_reason,
            raw_response=response,
        )

    def _translate_stream_chunk(self, chunk: Dict[str, Any]) -> StandardStreamChunk:
        """Traduce un chunk de streaming Cerebras al formato estándar."""
        delta = StandardStreamDelta()

        if "choices" in chunk and chunk["choices"]:
            choice = chunk["choices"][0]
            delta_data = choice.get("delta", {})

            delta.content = delta_data.get("content")
            delta.tool_calls = delta_data.get("tool_calls")
            delta.finish_reason = choice.get("finish_reason")

        # Extraer usage si está presente (último chunk)
        usage = None
        if "usage" in chunk and chunk["usage"]:
            usage_data = chunk["usage"]
            completion_details = usage_data.get("completion_tokens_details") or {}
            usage = StandardUsage(
                input_tokens=usage_data.get("prompt_tokens", 0),
                output_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                reasoning_tokens=completion_details.get("reasoning_tokens"),
            )

        return StandardStreamChunk(
            id=chunk.get("id", ""),
            model=chunk.get("model", ""),
            delta=delta,
            usage=usage,
        )
