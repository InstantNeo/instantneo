"""
Fetcher para OpenAI API.

Basado en la documentación oficial de /v1/responses endpoint.
"""

from typing import Any, Dict, List, Optional, Union, Literal, Iterator
import httpx
import json

# Importar todos los modelos de datos
from models.openai import (
    # Request models - Input content
    InputText,
    InputImage,
    InputFile,
    InputAudioData,
    InputAudio,
    InputMessage,
    # Request models - Tools
    FunctionTool,
    FileSearchTool,
    WebSearchTool,
    CodeInterpreterTool,
    ComputerUseTool,
    ImageGenerationTool,
    # Request models - Text formats
    TextFormat,
    JsonSchemaFormat,
    JsonObjectFormat,
    # Request models - Configuration
    TextConfig,
    ReasoningConfig,
    StreamOptions,
    PromptReference,
    Conversation,
    # Response models - Output content
    OutputText,
    ToolCall,
    Reasoning,
    OutputMessage,
    # Response models - Usage & details
    UsageDetails,
    Usage,
    IncompleteDetails,
    # Error models
    ErrorDetails,
    # Response models - Main response
    OpenAIResponse,
)


# ============================================================================
# CLIENTE PRINCIPAL
# ============================================================================

class OpenAIClient:
    """Cliente HTTP para OpenAI API"""

    BASE_URL = "https://api.openai.com/v1/responses"
    DEFAULT_TIMEOUT = 60.0

    def __init__(
        self,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 2
    ):
        """
        Inicializa el cliente de OpenAI.

        Args:
            api_key: API key de OpenAI
            timeout: Timeout en segundos para las requests
            max_retries: Número máximo de reintentos en caso de error
        """
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    def _build_headers(self) -> Dict[str, str]:
        """Construye los headers necesarios para la API"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_request_body(
        self,
        model: Optional[str] = None,
        input: Optional[Union[str, List[Union[InputMessage, Dict[str, Any]]]]] = None,
        background: Optional[bool] = None,
        conversation: Optional[Union[str, Conversation]] = None,
        include: Optional[List[str]] = None,
        max_completion_tokens: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None,
        parallel_tool_calls: Optional[bool] = None,
        previous_response_id: Optional[str] = None,
        prompt: Optional[PromptReference] = None,
        prompt_cache_key: Optional[str] = None,
        reasoning: Optional[ReasoningConfig] = None,
        safety_identifier: Optional[str] = None,
        service_tier: Optional[Literal["auto", "default", "flex", "priority"]] = None,
        store: Optional[bool] = None,
        stream: bool = False,
        stream_options: Optional[StreamOptions] = None,
        temperature: Optional[float] = None,
        text: Optional[TextConfig] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        tools: Optional[List[Union[FunctionTool, FileSearchTool, WebSearchTool, CodeInterpreterTool, ComputerUseTool, ImageGenerationTool, Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """Construye el body de la request según el esquema de OpenAI"""

        body: Dict[str, Any] = {}

        # Parámetros principales
        if model is not None:
            body["model"] = model

        if input is not None:
            if isinstance(input, str):
                body["input"] = input
            else:
                body["input"] = [
                    msg.__dict__ if hasattr(msg, '__dict__') else msg
                    for msg in input
                ]

        # Parámetros opcionales
        if background is not None:
            body["background"] = background

        if conversation is not None:
            if isinstance(conversation, str):
                body["conversation"] = conversation
            elif isinstance(conversation, Conversation):
                body["conversation"] = {"id": conversation.id}

        if include is not None:
            body["include"] = include

        if max_completion_tokens is not None:
            body["max_completion_tokens"] = max_completion_tokens

        if max_output_tokens is not None:
            body["max_output_tokens"] = max_output_tokens

        if metadata is not None:
            body["metadata"] = metadata

        if parallel_tool_calls is not None:
            body["parallel_tool_calls"] = parallel_tool_calls

        if previous_response_id is not None:
            body["previous_response_id"] = previous_response_id

        if prompt is not None:
            body["prompt"] = {
                "id": prompt.id,
                **({"variables": prompt.variables} if prompt.variables else {}),
                **({"version": prompt.version} if prompt.version else {})
            }

        if prompt_cache_key is not None:
            body["prompt_cache_key"] = prompt_cache_key

        if reasoning is not None:
            reasoning_dict = {}
            if reasoning.effort is not None:
                reasoning_dict["effort"] = reasoning.effort
            if reasoning.summary is not None:
                reasoning_dict["summary"] = reasoning.summary
            if reasoning_dict:
                body["reasoning"] = reasoning_dict

        if safety_identifier is not None:
            body["safety_identifier"] = safety_identifier

        if service_tier is not None:
            body["service_tier"] = service_tier

        if store is not None:
            body["store"] = store

        if stream:
            body["stream"] = stream

        if stream_options is not None:
            stream_opts = {}
            if stream_options.include_obfuscation is not None:
                stream_opts["include_obfuscation"] = stream_options.include_obfuscation
            if stream_opts:
                body["stream_options"] = stream_opts

        if temperature is not None:
            body["temperature"] = temperature

        if text is not None:
            text_dict = {}
            if text.format is not None:
                if isinstance(text.format, TextFormat):
                    text_dict["format"] = {"type": "text"}
                elif isinstance(text.format, JsonSchemaFormat):
                    text_dict["format"] = {
                        "type": "json_schema",
                        "name": text.format.name,
                        "schema": text.format.schema,
                        **({"description": text.format.description} if text.format.description else {}),
                        "strict": text.format.strict
                    }
                elif isinstance(text.format, JsonObjectFormat):
                    text_dict["format"] = {"type": "json_object"}
            if text.verbosity is not None:
                text_dict["verbosity"] = text.verbosity
            if text_dict:
                body["text"] = text_dict

        if tool_choice is not None:
            body["tool_choice"] = tool_choice

        if tools is not None:
            body["tools"] = [
                tool.__dict__ if hasattr(tool, '__dict__') else tool
                for tool in tools
            ]

        return body

    def _parse_response(self, response_data: Dict[str, Any]) -> OpenAIResponse:
        """Parsea la respuesta JSON a un objeto tipado"""

        # Parsear output
        output_items = []
        if "output" in response_data and response_data["output"]:
            for item in response_data["output"]:
                item_type = item.get("type")

                if item_type == "message":
                    # Parsear contenido del mensaje
                    content_list = []
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            content_list.append(OutputText(
                                text=content["text"],
                                annotations=content.get("annotations"),
                                logprobs=content.get("logprobs")
                            ))
                        else:
                            content_list.append(content)

                    output_items.append(OutputMessage(
                        content=content_list,
                        status=item.get("status")
                    ))

                elif item_type == "reasoning":
                    output_items.append(Reasoning(
                        summary=item.get("summary"),
                        content=item.get("content"),
                        encrypted_content=item.get("encrypted_content")
                    ))

                elif item_type in ["function", "file_search", "web_search_preview", "code_interpreter", "computer_use_preview", "image_generation"]:
                    output_items.append(ToolCall(
                        type=item_type,
                        id=item["id"],
                        name=item.get("name"),
                        arguments=item.get("arguments")
                    ))

                else:
                    # Tipo desconocido, guardarlo como dict
                    output_items.append(item)

        # Parsear usage
        usage = None
        if "usage" in response_data:
            usage_data = response_data["usage"]

            prompt_details = None
            if "prompt_tokens_details" in usage_data:
                ptd = usage_data["prompt_tokens_details"]
                prompt_details = UsageDetails(
                    audio_tokens=ptd.get("audio_tokens"),
                    text_tokens=ptd.get("text_tokens"),
                    cached_tokens=ptd.get("cached_tokens")
                )

            completion_details = None
            if "completion_tokens_details" in usage_data:
                ctd = usage_data["completion_tokens_details"]
                completion_details = UsageDetails(
                    audio_tokens=ctd.get("audio_tokens"),
                    reasoning_tokens=ctd.get("reasoning_tokens"),
                    text_tokens=ctd.get("text_tokens")
                )

            usage = Usage(
                prompt_tokens=usage_data["prompt_tokens"],
                completion_tokens=usage_data["completion_tokens"],
                total_tokens=usage_data["total_tokens"],
                prompt_tokens_details=prompt_details,
                completion_tokens_details=completion_details
            )

        # Parsear incomplete_details
        incomplete_details = None
        if "incomplete_details" in response_data:
            incomplete_details = IncompleteDetails(
                reason=response_data["incomplete_details"]["reason"]
            )

        # Parsear error
        error = None
        if "error" in response_data:
            error = ErrorDetails(
                code=response_data["error"]["code"],
                message=response_data["error"]["message"]
            )

        # Parsear conversation
        conversation = None
        if "conversation" in response_data and response_data["conversation"]:
            conversation = Conversation(id=response_data["conversation"]["id"])

        # Parsear prompt
        prompt = None
        if "prompt" in response_data and response_data["prompt"]:
            prompt_data = response_data["prompt"]
            prompt = PromptReference(
                id=prompt_data["id"],
                variables=prompt_data.get("variables"),
                version=prompt_data.get("version")
            )

        # Parsear reasoning config
        reasoning_config = None
        if "reasoning" in response_data and response_data["reasoning"]:
            reasoning_config = ReasoningConfig(
                effort=response_data["reasoning"].get("effort"),
                summary=response_data["reasoning"].get("summary")
            )

        # Parsear text config
        text_config = None
        if "text" in response_data and response_data["text"]:
            text_data = response_data["text"]
            text_format = None

            if "format" in text_data:
                fmt = text_data["format"]
                fmt_type = fmt.get("type")

                if fmt_type == "text":
                    text_format = TextFormat()
                elif fmt_type == "json_schema":
                    text_format = JsonSchemaFormat(
                        name=fmt["name"],
                        schema=fmt["schema"],
                        description=fmt.get("description"),
                        strict=fmt.get("strict", False)
                    )
                elif fmt_type == "json_object":
                    text_format = JsonObjectFormat()

            text_config = TextConfig(
                format=text_format,
                verbosity=text_data.get("verbosity", "medium")
            )

        return OpenAIResponse(
            id=response_data["id"],
            object=response_data.get("object", "response"),
            model=response_data["model"],
            created_at=response_data["created_at"],
            status=response_data["status"],
            output=output_items if output_items else None,
            output_text=response_data.get("output_text"),
            usage=usage,
            incomplete_details=incomplete_details,
            error=error,
            background=response_data.get("background"),
            conversation=conversation,
            instructions=response_data.get("instructions"),
            max_output_tokens=response_data.get("max_output_tokens"),
            max_tool_calls=response_data.get("max_tool_calls"),
            metadata=response_data.get("metadata"),
            parallel_tool_calls=response_data.get("parallel_tool_calls"),
            previous_response_id=response_data.get("previous_response_id"),
            prompt=prompt,
            prompt_cache_key=response_data.get("prompt_cache_key"),
            reasoning=reasoning_config,
            safety_identifier=response_data.get("safety_identifier"),
            service_tier=response_data.get("service_tier"),
            temperature=response_data.get("temperature"),
            text=text_config,
            tool_choice=response_data.get("tool_choice"),
            tools=response_data.get("tools"),
            top_logprobs=response_data.get("top_logprobs"),
            top_p=response_data.get("top_p"),
            truncation=response_data.get("truncation")
        )

    def create_completion(
        self,
        model: Optional[str] = None,
        input: Optional[Union[str, List[Union[InputMessage, Dict[str, Any]]]]] = None,
        background: Optional[bool] = None,
        conversation: Optional[Union[str, Conversation]] = None,
        include: Optional[List[str]] = None,
        max_completion_tokens: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None,
        parallel_tool_calls: Optional[bool] = None,
        previous_response_id: Optional[str] = None,
        prompt: Optional[PromptReference] = None,
        prompt_cache_key: Optional[str] = None,
        reasoning: Optional[ReasoningConfig] = None,
        safety_identifier: Optional[str] = None,
        service_tier: Optional[Literal["auto", "default", "flex", "priority"]] = None,
        store: Optional[bool] = None,
        stream: bool = False,
        stream_options: Optional[StreamOptions] = None,
        temperature: Optional[float] = None,
        text: Optional[TextConfig] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        tools: Optional[List[Union[FunctionTool, FileSearchTool, WebSearchTool, CodeInterpreterTool, ComputerUseTool, ImageGenerationTool, Dict[str, Any]]]] = None,
    ) -> OpenAIResponse:
        """
        Crea una completion usando la API de OpenAI.

        Args:
            model: ID del modelo (ej: "gpt-4o", "o3")
            input: Entrada de texto simple o lista de mensajes
            background: Si ejecutar la respuesta en segundo plano
            conversation: Conversación a la que pertenece esta respuesta
            include: Datos adicionales a incluir en la respuesta
            max_completion_tokens: Número máximo de tokens de finalización
            max_output_tokens: Número máximo de tokens totales (incluye razonamiento)
            metadata: Metadatos adicionales (hasta 16 pares clave-valor)
            parallel_tool_calls: Si permitir llamadas a herramientas en paralelo
            previous_response_id: ID de la respuesta anterior para conversaciones multi-turno
            prompt: Referencia a plantilla de prompt
            prompt_cache_key: Clave para optimización de caché
            reasoning: Configuración de razonamiento (solo modelos gpt-5 y serie-o)
            safety_identifier: Identificador para detección de abuso
            service_tier: Nivel de servicio ("auto", "default", "flex", "priority")
            store: Si almacenar la respuesta para recuperación posterior
            stream: Si usar streaming (usar create_completion_stream para streaming)
            stream_options: Opciones de streaming
            temperature: Control de aleatoriedad (0-2)
            text: Configuración de formato de texto
            tool_choice: Control de selección de herramientas
            tools: Lista de herramientas disponibles

        Returns:
            OpenAIResponse con la respuesta del modelo

        Raises:
            httpx.HTTPStatusError: Si la API devuelve un error HTTP
            ValueError: Si los parámetros son inválidos
        """

        headers = self._build_headers()
        body = self._build_request_body(
            model=model,
            input=input,
            background=background,
            conversation=conversation,
            include=include,
            max_completion_tokens=max_completion_tokens,
            max_output_tokens=max_output_tokens,
            metadata=metadata,
            parallel_tool_calls=parallel_tool_calls,
            previous_response_id=previous_response_id,
            prompt=prompt,
            prompt_cache_key=prompt_cache_key,
            reasoning=reasoning,
            safety_identifier=safety_identifier,
            service_tier=service_tier,
            store=store,
            stream=stream,
            stream_options=stream_options,
            temperature=temperature,
            text=text,
            tool_choice=tool_choice,
            tools=tools,
        )

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                self.BASE_URL,
                headers=headers,
                json=body
            )

            # Manejar errores HTTP
            if response.status_code != 200:
                try:
                    error_data = response.json()
                    error_message = error_data.get('error', {}).get('message', 'Unknown error')
                except:
                    error_message = f"HTTP {response.status_code}: {response.text}"

                raise httpx.HTTPStatusError(
                    f"OpenAI API error: {error_message}",
                    request=response.request,
                    response=response
                )

            response_data = response.json()
            return self._parse_response(response_data)

    def create_completion_stream(
        self,
        model: Optional[str] = None,
        input: Optional[Union[str, List[Union[InputMessage, Dict[str, Any]]]]] = None,
        background: Optional[bool] = None,
        conversation: Optional[Union[str, Conversation]] = None,
        include: Optional[List[str]] = None,
        max_completion_tokens: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None,
        parallel_tool_calls: Optional[bool] = None,
        previous_response_id: Optional[str] = None,
        prompt: Optional[PromptReference] = None,
        prompt_cache_key: Optional[str] = None,
        reasoning: Optional[ReasoningConfig] = None,
        safety_identifier: Optional[str] = None,
        service_tier: Optional[Literal["auto", "default", "flex", "priority"]] = None,
        store: Optional[bool] = None,
        stream_options: Optional[StreamOptions] = None,
        temperature: Optional[float] = None,
        text: Optional[TextConfig] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        tools: Optional[List[Union[FunctionTool, FileSearchTool, WebSearchTool, CodeInterpreterTool, ComputerUseTool, ImageGenerationTool, Dict[str, Any]]]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Crea una completion con streaming (server-sent events).

        Args:
            model: ID del modelo
            input: Entrada de texto simple o lista de mensajes
            background: Si ejecutar la respuesta en segundo plano
            conversation: Conversación a la que pertenece esta respuesta
            include: Datos adicionales a incluir en la respuesta
            max_completion_tokens: Número máximo de tokens de finalización
            max_output_tokens: Número máximo de tokens totales (incluye razonamiento)
            metadata: Metadatos adicionales (hasta 16 pares clave-valor)
            parallel_tool_calls: Si permitir llamadas a herramientas en paralelo
            previous_response_id: ID de la respuesta anterior para conversaciones multi-turno
            prompt: Referencia a plantilla de prompt
            prompt_cache_key: Clave para optimización de caché
            reasoning: Configuración de razonamiento (solo modelos gpt-5 y serie-o)
            safety_identifier: Identificador para detección de abuso
            service_tier: Nivel de servicio ("auto", "default", "flex", "priority")
            store: Si almacenar la respuesta para recuperación posterior
            stream_options: Opciones de streaming
            temperature: Control de aleatoriedad (0-2)
            text: Configuración de formato de texto
            tool_choice: Control de selección de herramientas
            tools: Lista de herramientas disponibles

        Yields:
            Dict con eventos de streaming
        """

        headers = self._build_headers()
        body = self._build_request_body(
            model=model,
            input=input,
            background=background,
            conversation=conversation,
            include=include,
            max_completion_tokens=max_completion_tokens,
            max_output_tokens=max_output_tokens,
            metadata=metadata,
            parallel_tool_calls=parallel_tool_calls,
            previous_response_id=previous_response_id,
            prompt=prompt,
            prompt_cache_key=prompt_cache_key,
            reasoning=reasoning,
            safety_identifier=safety_identifier,
            service_tier=service_tier,
            store=store,
            stream=True,
            stream_options=stream_options,
            temperature=temperature,
            text=text,
            tool_choice=tool_choice,
            tools=tools,
        )

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", self.BASE_URL, headers=headers, json=body) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remover "data: "
                        if data.strip() == "[DONE]":
                            break
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue


# ============================================================================
# FUNCIÓN DE CONVENIENCIA
# ============================================================================

def fetch_openai(
    api_key: str,
    model: Optional[str] = None,
    input: Optional[Union[str, List[Union[InputMessage, Dict[str, Any]]]]] = None,
    stream: bool = False,
    background: Optional[bool] = None,
    conversation: Optional[Union[str, Conversation]] = None,
    include: Optional[List[str]] = None,
    max_completion_tokens: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
    metadata: Optional[Dict[str, str]] = None,
    parallel_tool_calls: Optional[bool] = None,
    previous_response_id: Optional[str] = None,
    prompt: Optional[PromptReference] = None,
    prompt_cache_key: Optional[str] = None,
    reasoning: Optional[ReasoningConfig] = None,
    safety_identifier: Optional[str] = None,
    service_tier: Optional[Literal["auto", "default", "flex", "priority"]] = None,
    store: Optional[bool] = None,
    stream_options: Optional[StreamOptions] = None,
    temperature: Optional[float] = None,
    text: Optional[TextConfig] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    tools: Optional[List[Union[FunctionTool, FileSearchTool, WebSearchTool, CodeInterpreterTool, ComputerUseTool, ImageGenerationTool, Dict[str, Any]]]] = None,
) -> Union[OpenAIResponse, Iterator[Dict[str, Any]]]:
    """
    Función de conveniencia para hacer requests a OpenAI API.

    Args:
        api_key: API key de OpenAI
        model: ID del modelo a usar (ej: "gpt-4o", "o3")
        input: Entrada de texto simple o lista de mensajes
        stream: Si usar streaming o no
        background: Si ejecutar la respuesta en segundo plano
        conversation: Conversación a la que pertenece esta respuesta
        include: Datos adicionales a incluir en la respuesta
        max_completion_tokens: Número máximo de tokens de finalización
        max_output_tokens: Número máximo de tokens totales (incluye razonamiento)
        metadata: Metadatos adicionales (hasta 16 pares clave-valor)
        parallel_tool_calls: Si permitir llamadas a herramientas en paralelo
        previous_response_id: ID de la respuesta anterior para conversaciones multi-turno
        prompt: Referencia a plantilla de prompt
        prompt_cache_key: Clave para optimización de caché
        reasoning: Configuración de razonamiento (solo modelos gpt-5 y serie-o)
        safety_identifier: Identificador para detección de abuso
        service_tier: Nivel de servicio ("auto", "default", "flex", "priority")
        store: Si almacenar la respuesta para recuperación posterior
        stream_options: Opciones de streaming
        temperature: Control de aleatoriedad (0-2)
        text: Configuración de formato de texto
        tool_choice: Control de selección de herramientas
        tools: Lista de herramientas disponibles

    Returns:
        OpenAIResponse si stream=False
        Iterator[Dict] si stream=True

    Example:
        >>> from fetchers.openai import fetch_openai, InputMessage
        >>>
        >>> response = fetch_openai(
        ...     api_key="sk-proj-...",
        ...     model="gpt-4o",
        ...     input="Hello, GPT!",
        ...     temperature=0.7
        ... )
        >>> print(response.output_text)

        >>> # Con mensajes estructurados
        >>> response = fetch_openai(
        ...     api_key="sk-proj-...",
        ...     model="gpt-4o",
        ...     input=[
        ...         InputMessage(role="user", content="What is the capital of France?")
        ...     ],
        ...     max_output_tokens=100
        ... )
        >>> print(response.output[0].content[0].text)
    """

    client = OpenAIClient(api_key=api_key)

    if stream:
        return client.create_completion_stream(
            model=model,
            input=input,
            background=background,
            conversation=conversation,
            include=include,
            max_completion_tokens=max_completion_tokens,
            max_output_tokens=max_output_tokens,
            metadata=metadata,
            parallel_tool_calls=parallel_tool_calls,
            previous_response_id=previous_response_id,
            prompt=prompt,
            prompt_cache_key=prompt_cache_key,
            reasoning=reasoning,
            safety_identifier=safety_identifier,
            service_tier=service_tier,
            store=store,
            stream_options=stream_options,
            temperature=temperature,
            text=text,
            tool_choice=tool_choice,
            tools=tools,
        )
    else:
        return client.create_completion(
            model=model,
            input=input,
            background=background,
            conversation=conversation,
            include=include,
            max_completion_tokens=max_completion_tokens,
            max_output_tokens=max_output_tokens,
            metadata=metadata,
            parallel_tool_calls=parallel_tool_calls,
            previous_response_id=previous_response_id,
            prompt=prompt,
            prompt_cache_key=prompt_cache_key,
            reasoning=reasoning,
            safety_identifier=safety_identifier,
            service_tier=service_tier,
            store=store,
            stream=False,
            stream_options=stream_options,
            temperature=temperature,
            text=text,
            tool_choice=tool_choice,
            tools=tools,
        )
