"""
Adapter para Google Gemini API (Google AI Studio, con API Key).

Para Gemini hosteado en Vertex AI ver `adapters/vertex_gemini_adapter.py`,
que hereda de este y solo intercambia el cliente HTTP.

Diferencias clave de Gemini:
- Los mensajes usan "parts" en lugar de "content" directo
- El rol "assistant" se mapea a "model"
- System instruction es un parámetro separado (no va en contents)
- Tools usan "functionDeclarations" dentro de "tools"
- No hay IDs de tool calls (se generan en el adapter)
"""

from typing import Iterator, Dict, Any, List, Optional, Union
import json
import uuid

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
from instantneo.models.gemini import (
    Part,
    Content,
    FunctionDeclaration,
    GenerationConfig,
    GeminiResponse,
)


class GeminiAdapter(BaseAdapter):
    """
    Adapter para Google Gemini API (Google AI Studio, con API Key).

    Uso:
        adapter = GeminiAdapter(api_key="AI...")

    Para Vertex AI ver `VertexGeminiAdapter`, que hereda de éste y solo
    intercambia el cliente HTTP.
    """

    def __init__(self, api_key: str):
        """
        Args:
            api_key: API key de Google AI Studio.
        """
        from instantneo.fetchers.gemini import GeminiClient
        self.client = GeminiClient(api_key=api_key)

    def complete(self, request: StandardRequest) -> StandardResponse:
        """
        Ejecuta una completion usando Gemini API.

        Args:
            request: Petición en formato estándar

        Returns:
            StandardResponse con la respuesta del modelo
        """
        try:
            # Extraer system instruction y traducir mensajes
            system_instruction, gemini_contents = self._translate_messages(request.messages)

            # Traducir tools
            gemini_tools = self._translate_tools(request.tools) if request.tools else None
            gemini_tool_config = self._translate_tool_choice(request.tool_choice) if request.tool_choice else None

            # Construir generation config
            gen_config = self._build_generation_config(request)

            # Llamar al fetcher
            response = self.client.generate_content(
                model=request.model,
                contents=gemini_contents,
                generation_config=gen_config,
                system_instruction=system_instruction,
                tools=gemini_tools,
                tool_config=gemini_tool_config,
            )

            # Traducir respuesta Gemini → formato estándar
            return self._translate_response(response, request.model)

        except Exception as e:
            raise RuntimeError(f"Error en Gemini API: {e}") from e

    def complete_stream(self, request: StandardRequest) -> Iterator[StandardStreamChunk]:
        """
        Ejecuta una completion con streaming usando Gemini API.

        Args:
            request: Petición en formato estándar

        Yields:
            StandardStreamChunk con fragmentos de la respuesta
        """
        try:
            # Extraer system instruction y traducir mensajes
            system_instruction, gemini_contents = self._translate_messages(request.messages)

            # Traducir tools
            gemini_tools = self._translate_tools(request.tools) if request.tools else None
            gemini_tool_config = self._translate_tool_choice(request.tool_choice) if request.tool_choice else None

            # Construir generation config
            gen_config = self._build_generation_config(request)

            # Llamar al fetcher con streaming
            stream = self.client.generate_content_stream(
                model=request.model,
                contents=gemini_contents,
                generation_config=gen_config,
                system_instruction=system_instruction,
                tools=gemini_tools,
                tool_config=gemini_tool_config,
            )

            # Traducir chunks
            for chunk in stream:
                translated = self._translate_stream_chunk(chunk, request.model)
                if translated:
                    yield translated

        except Exception as e:
            raise RuntimeError(f"Error en Gemini API streaming: {e}") from e

    def supports_images(self) -> bool:
        """Gemini soporta imágenes."""
        return True

    def get_provider_name(self) -> str:
        """Devuelve el nombre del proveedor."""
        return "gemini"

    # =========================================================================
    # MÉTODOS DE TRADUCCIÓN: StandardRequest → Gemini
    # =========================================================================

    def _translate_messages(self, messages: List) -> tuple:
        """
        Extrae el system instruction y convierte mensajes al formato Gemini.

        Gemini requiere que system sea un parámetro separado, no un mensaje.

        Returns:
            Tuple de (system_instruction, list_of_contents)
        """
        system_parts = []
        gemini_contents = []

        for msg in messages:
            if msg.role == "system":
                # Acumular contenido de sistema
                if isinstance(msg.content, str):
                    system_parts.append(msg.content)
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if hasattr(block, 'text'):
                            system_parts.append(block.text)
                        elif isinstance(block, dict) and 'text' in block:
                            system_parts.append(block['text'])

            elif msg.role == "tool":
                # Resultado de función → functionResponse
                # Gemini espera que el resultado vaya como un mensaje "user" con functionResponse
                response_content = msg.content
                if isinstance(response_content, str):
                    try:
                        response_content = json.loads(response_content)
                    except json.JSONDecodeError:
                        response_content = {"result": response_content}

                gemini_contents.append(Content(
                    role="user",
                    parts=[Part(function_response={
                        "name": msg.name or "function",
                        "response": response_content
                    })]
                ))

            else:
                # user o assistant
                role = "model" if msg.role == "assistant" else "user"
                parts = self._translate_content_to_parts(msg.content)

                # Agregar tool_calls como function_call parts
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        try:
                            args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                        except json.JSONDecodeError:
                            args = {}
                        parts.append(Part(function_call={
                            "name": tc.name,
                            "args": args
                        }))

                gemini_contents.append(Content(role=role, parts=parts))

        system_instruction = "\n".join(system_parts) if system_parts else None
        return system_instruction, gemini_contents

    def _translate_content_to_parts(self, content: Union[str, List]) -> List[Part]:
        """Traduce content blocks a parts de Gemini."""
        if isinstance(content, str):
            return [Part(text=content)]

        if content is None:
            return []

        parts = []
        for block in content:
            if hasattr(block, 'type'):
                # Objetos TextContent/ImageContent
                if block.type == "text":
                    parts.append(Part(text=block.text))
                elif block.type == "image":
                    if block.base64 and block.media_type:
                        parts.append(Part(inline_data={
                            "mimeType": block.media_type,
                            "data": block.base64
                        }))
                    elif block.url:
                        # Para URLs, Gemini espera fileData con fileUri
                        # Nota: En producción, image_utils convierte URLs a base64
                        parts.append(Part(file_data={
                            "mimeType": block.media_type or "image/jpeg",
                            "fileUri": block.url
                        }))

            elif isinstance(block, dict):
                block_type = block.get("type", "")

                if block_type == "text":
                    parts.append(Part(text=block.get("text", "")))

                elif block_type == "image_url":
                    # Formato legacy de OpenAI Chat Completions
                    image_data = block.get("image_url", {})
                    url = image_data.get("url", "") if isinstance(image_data, dict) else image_data

                    if url.startswith("data:"):
                        # Es base64: data:image/jpeg;base64,xxxx
                        try:
                            header, base64_data = url.split(";base64,", 1)
                            mime_type = header.replace("data:", "")
                            parts.append(Part(inline_data={
                                "mimeType": mime_type,
                                "data": base64_data
                            }))
                        except ValueError:
                            pass
                    else:
                        # Es URL directa
                        parts.append(Part(file_data={
                            "mimeType": "image/jpeg",
                            "fileUri": url
                        }))

                elif block_type == "image":
                    # Formato con source
                    source = block.get("source", {})
                    if source.get("type") == "base64":
                        parts.append(Part(inline_data={
                            "mimeType": source.get("media_type", "image/jpeg"),
                            "data": source.get("data", "")
                        }))
                    elif source.get("type") == "url":
                        parts.append(Part(file_data={
                            "mimeType": source.get("media_type", "image/jpeg"),
                            "fileUri": source.get("url", "")
                        }))

        return parts if parts else [Part(text="")]

    def _translate_tools(self, tools: List) -> List[FunctionDeclaration]:
        """Traduce herramientas estándar al formato Gemini."""
        return [
            FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
            )
            for tool in tools
        ]

    def _translate_tool_choice(self, tool_choice) -> Dict[str, Any]:
        """Traduce tool_choice estándar al formato Gemini."""
        config = {"functionCallingConfig": {}}

        if tool_choice.type == "auto":
            config["functionCallingConfig"]["mode"] = "AUTO"
        elif tool_choice.type == "none":
            config["functionCallingConfig"]["mode"] = "NONE"
        elif tool_choice.type == "required":
            config["functionCallingConfig"]["mode"] = "ANY"
        elif tool_choice.type == "specific" and tool_choice.name:
            config["functionCallingConfig"]["mode"] = "ANY"
            config["functionCallingConfig"]["allowedFunctionNames"] = [tool_choice.name]
        else:
            config["functionCallingConfig"]["mode"] = "AUTO"

        return config

    def _build_generation_config(self, request: StandardRequest) -> Optional[GenerationConfig]:
        """Construye la configuración de generación."""
        config = GenerationConfig(
            temperature=request.temperature,
            top_p=request.top_p,
            max_output_tokens=request.max_tokens,
            stop_sequences=request.stop,
        )

        # Agregar thinking config si hay reasoning
        if request.reasoning:
            self._warn_unsupported_reasoning_keys(request.reasoning, {"effort", "budget_tokens"})
            budget = request.reasoning.get("budget_tokens")
            if not budget:
                effort_map = {"low": 1024, "medium": 4096, "high": 10240}
                budget = effort_map.get(request.reasoning.get("effort", "medium"), 4096)
            config.thinking_config = {"thinkingBudget": budget}

        # Solo retornar si hay al menos un parámetro configurado
        if any([
            config.temperature is not None,
            config.top_p is not None,
            config.max_output_tokens is not None,
            config.stop_sequences,
            getattr(config, 'thinking_config', None),
        ]):
            return config
        return None

    # =========================================================================
    # MÉTODOS DE TRADUCCIÓN: Gemini → StandardResponse
    # =========================================================================

    def _translate_response(self, response: GeminiResponse, model: str) -> StandardResponse:
        """Traduce respuesta Gemini al formato estándar."""
        candidate = response.candidates[0]

        # Extraer texto, reasoning y function calls
        text_content = ""
        reasoning_content = ""
        tool_calls = []

        for i, part in enumerate(candidate.content.parts):
            if getattr(part, 'thought', False) and part.text:
                # Part with thought=True is reasoning content
                reasoning_content += part.text
            elif part.text:
                text_content += part.text
            elif part.function_call:
                # Gemini no genera IDs, creamos uno
                tool_calls.append(StandardToolCall(
                    id=f"call_{uuid.uuid4().hex[:12]}",
                    name=part.function_call.get("name", ""),
                    arguments=json.dumps(part.function_call.get("args", {})),
                ))

        response_message = StandardResponseMessage(
            content=text_content if text_content else None,
            tool_calls=tool_calls if tool_calls else None,
            reasoning=reasoning_content if reasoning_content else None,
        )

        standard_choice = StandardChoice(
            message=response_message,
            finish_reason=self._translate_finish_reason(candidate.finish_reason),
            index=0,
        )

        return StandardResponse(
            id=f"gemini_{uuid.uuid4().hex[:12]}",
            model=response.model_version or model,
            choices=[standard_choice],
            usage=StandardUsage(
                input_tokens=response.usage_metadata.prompt_token_count,
                output_tokens=response.usage_metadata.candidates_token_count,
                total_tokens=response.usage_metadata.total_token_count,
                # Gemini 2.5+ expone thoughts_token_count en usage_metadata.
                # Para modelos anteriores el atributo no existe; getattr → None.
                reasoning_tokens=getattr(response.usage_metadata, 'thoughts_token_count', None),
            ),
            finish_reason=self._translate_finish_reason(candidate.finish_reason),
            raw_response=response,
        )

    def _translate_finish_reason(self, finish_reason: Optional[str]) -> str:
        """Traduce finish_reason de Gemini al formato estándar."""
        mapping = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
            "BLOCKLIST": "content_filter",
            "OTHER": "unknown",
        }
        return mapping.get(finish_reason, finish_reason or "unknown")

    def _translate_stream_chunk(self, chunk: Dict[str, Any], model: str) -> Optional[StandardStreamChunk]:
        """Traduce un chunk de streaming Gemini al formato estándar."""
        delta = StandardStreamDelta()

        candidates = chunk.get("candidates", [])
        if not candidates:
            return None

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        for part in parts:
            if part.get("thought") and "text" in part:
                # Thought part is reasoning content
                delta.reasoning = (delta.reasoning or "") + part["text"]
            elif "text" in part:
                delta.content = (delta.content or "") + part["text"]
            elif "functionCall" in part:
                # Tool call en streaming
                fc = part["functionCall"]
                delta.tool_calls = [{
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "name": fc.get("name", ""),
                    "arguments": json.dumps(fc.get("args", {})),
                }]

        # Finish reason
        if "finishReason" in candidate:
            delta.finish_reason = self._translate_finish_reason(candidate["finishReason"])

        # Usage
        usage = None
        if "usageMetadata" in chunk:
            usage_data = chunk["usageMetadata"]
            usage = StandardUsage(
                input_tokens=usage_data.get("promptTokenCount", 0),
                output_tokens=usage_data.get("candidatesTokenCount", 0),
                total_tokens=usage_data.get("totalTokenCount", 0),
                # Gemini 2.5+ raw API: thoughtsTokenCount.
                reasoning_tokens=usage_data.get("thoughtsTokenCount"),
            )

        # Si no hay contenido relevante, retornar None
        if delta.content is None and delta.tool_calls is None and delta.reasoning is None and delta.finish_reason is None:
            return None

        return StandardStreamChunk(
            id=f"gemini_{uuid.uuid4().hex[:8]}",
            model=model,
            delta=delta,
            usage=usage,
        )
