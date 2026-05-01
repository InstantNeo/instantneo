"""
Base interna para adapters de providers OpenAI chat/completions.

Encapsula la traducción StandardRequest ↔ formato chat/completions y la
mecánica genérica de complete()/complete_stream(). Cada provider concreto
hereda y solo declara cómo construir su cliente HTTP y su nombre.

Subclases conocidas:
    adapters/groq_adapter.py        → GroqAdapter
    adapters/xai_adapter.py         → XAIAdapter
    adapters/vertex_xai_adapter.py  → VertexXAIAdapter

El módulo lleva prefijo "_" para señalizar que es base interna; no se
expone como provider público (no se usa con `InstantNeo(provider="...")`).
"""

from typing import Any, Dict, Iterator, List

from instantneo.adapters.base_adapter import BaseAdapter
from instantneo.fetchers._chat_completions import (
    Message,
    Tool,
    ToolFunction,
)
from instantneo.models.standard import (
    StandardChoice,
    StandardRequest,
    StandardResponse,
    StandardResponseMessage,
    StandardStreamChunk,
    StandardStreamDelta,
    StandardToolCall,
    StandardUsage,
)


class ChatCompletionsAdapter(BaseAdapter):
    """
    Adapter base interno para providers que usan el wire format
    OpenAI chat/completions clásico (Groq, xAI, Mistral, DeepSeek,
    Together AI, Fireworks, Perplexity, etc.).

    Cada subclase concreta debe:
    - Asignar `self.client` en `__init__`.
    - Implementar `get_provider_name()`.

    No se instancia directamente.
    """

    def __init__(self):
        if type(self) is ChatCompletionsAdapter:
            raise TypeError(
                "ChatCompletionsAdapter es una clase base interna; "
                "usa una subclase concreta (GroqAdapter, XAIAdapter, etc.)."
            )
        # self.client se asigna en la subclase

    # ─── API pública del adapter ────────────────────────────────────────────

    def complete(self, request: StandardRequest) -> StandardResponse:
        """Completion non-stream."""
        try:
            messages = self._translate_messages(request.messages)
            tools = self._translate_tools(request.tools) if request.tools else None
            tool_choice = (
                self._translate_tool_choice(request.tool_choice)
                if request.tool_choice else None
            )

            extra_params = dict(request.provider_params)
            if request.reasoning:
                self._warn_unsupported_reasoning_keys(request.reasoning, {"effort"})
                extra_params["reasoning_effort"] = request.reasoning.get("effort", "medium")

            response = self.client.create_chat_completion(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_completion_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=request.stop,
                seed=request.seed,
                tools=tools,
                tool_choice=tool_choice,
                **extra_params,
            )
            return self._translate_response(response)
        except Exception as e:
            raise RuntimeError(f"Error en {self.get_provider_name()} API: {e}")

    def complete_stream(self, request: StandardRequest) -> Iterator[StandardStreamChunk]:
        """Completion streaming."""
        try:
            messages = self._translate_messages(request.messages)
            tools = self._translate_tools(request.tools) if request.tools else None
            tool_choice = (
                self._translate_tool_choice(request.tool_choice)
                if request.tool_choice else None
            )

            extra_params = dict(request.provider_params)
            if request.reasoning:
                self._warn_unsupported_reasoning_keys(request.reasoning, {"effort"})
                extra_params["reasoning_effort"] = request.reasoning.get("effort", "medium")

            stream = self.client.create_chat_completion_stream(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_completion_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=request.stop,
                seed=request.seed,
                tools=tools,
                tool_choice=tool_choice,
                **extra_params,
            )
            for chunk in stream:
                yield self._translate_stream_chunk(chunk)
        except Exception as e:
            raise RuntimeError(f"Error en {self.get_provider_name()} API streaming: {e}")

    def supports_images(self) -> bool:
        """La mayoría de chat/completions providers ya soportan imágenes."""
        return True

    # ─── Traducciones StandardRequest → chat/completions ─────────────────────

    def _translate_messages(self, messages: List) -> List[Message]:
        """StandardMessage → Message (chat/completions wire)."""
        out = []
        for msg in messages:
            content = msg.content
            if isinstance(content, list):
                content = self._translate_content_blocks(content)

            wire_msg = Message(
                role=msg.role,
                content=content,
                name=msg.name,
                tool_call_id=msg.tool_call_id,
            )

            if msg.tool_calls:
                wire_msg.tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]

            out.append(wire_msg)
        return out

    def _translate_content_blocks(self, blocks: List) -> List[Dict[str, Any]]:
        """Content blocks estándar → formato OpenAI chat/completions."""
        result = []

        for block in blocks:
            if hasattr(block, "type"):
                if block.type == "text":
                    result.append({"type": "text", "text": block.text})
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
                    result.append({"type": "text", "text": block.get("text", "")})
                elif block_type == "image_url":
                    result.append(block)
                elif block_type == "image":
                    source = block.get("source", {})
                    if source.get("type") == "url":
                        result.append({
                            "type": "image_url",
                            "image_url": {"url": source.get("url", "")},
                        })
                    elif source.get("type") == "base64":
                        url = (
                            f"data:{source.get('media_type', '')};"
                            f"base64,{source.get('data', '')}"
                        )
                        result.append({
                            "type": "image_url",
                            "image_url": {"url": url},
                        })
                else:
                    result.append(block)

        return result

    def _translate_tools(self, tools: List) -> List[Tool]:
        """StandardTool → Tool (chat/completions function calling)."""
        return [
            Tool(
                type="function",
                function=ToolFunction(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.parameters,
                ),
            )
            for tool in tools
        ]

    def _translate_tool_choice(self, tool_choice) -> Any:
        """StandardToolChoice → tool_choice del wire chat/completions."""
        if tool_choice.type == "auto":
            return "auto"
        elif tool_choice.type == "none":
            return "none"
        elif tool_choice.type == "required":
            return "required"
        elif tool_choice.type == "specific" and tool_choice.name:
            return {"type": "function", "function": {"name": tool_choice.name}}
        return "auto"

    # ─── Traducciones chat/completions → StandardResponse ────────────────────

    def _translate_response(self, response) -> StandardResponse:
        """ChatCompletionResponse → StandardResponse."""
        choice = response.choices[0] if response.choices else None

        usage = StandardUsage(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            reasoning_tokens=response.usage.reasoning_tokens,
        )

        if not choice:
            return StandardResponse(
                id=response.id,
                model=response.model,
                choices=[],
                usage=usage,
                finish_reason="error",
                raw_response=response,
            )

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

        response_message = StandardResponseMessage(
            content=choice.message.content,
            tool_calls=tool_calls,
            reasoning=choice.message.reasoning,
        )

        standard_choice = StandardChoice(
            message=response_message,
            finish_reason=choice.finish_reason,
            index=choice.index,
        )

        return StandardResponse(
            id=response.id,
            model=response.model,
            choices=[standard_choice],
            usage=usage,
            finish_reason=choice.finish_reason,
            raw_response=response,
        )

    def _translate_stream_chunk(self, chunk: Dict[str, Any]) -> StandardStreamChunk:
        """Chunk SSE → StandardStreamChunk."""
        delta = StandardStreamDelta()

        if "choices" in chunk and chunk["choices"]:
            choice = chunk["choices"][0]
            delta_data = choice.get("delta", {})
            delta.content = delta_data.get("content")
            delta.tool_calls = delta_data.get("tool_calls")
            delta.finish_reason = choice.get("finish_reason")

        usage = None
        if chunk.get("usage"):
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
