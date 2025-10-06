"""
Fetcher para Groq API.

Basado en la documentación oficial de /openai/v1/chat/completions endpoint.
Compatible con el formato de OpenAI con extensiones específicas de Groq.
"""

from typing import Any, Dict, List, Optional, Union, Literal, Iterator
import httpx
import json

from models.groq import (
    Message,
    Tool,
    ToolFunction,
    Document,
    SearchSettings,
    FunctionCall,
    ToolCall,
    ResponseMessage,
    Choice,
    Usage,
    GroqResponse,
    GroqError,
)


# ============================================================================
# CLIENTE PRINCIPAL
# ============================================================================

class GroqClient:
    """Cliente HTTP para Groq API"""

    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    DEFAULT_TIMEOUT = 60.0

    def __init__(
        self,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 2
    ):
        """
        Inicializa el cliente de Groq.

        Args:
            api_key: API key de Groq
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
        messages: List[Message],
        model: str,
        temperature: Optional[float] = None,
        max_completion_tokens: Optional[int] = None,
        stream: bool = False,
        stream_options: Optional[Dict[str, Any]] = None,
        stop: Optional[Union[str, List[str]]] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        parallel_tool_calls: Optional[bool] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        user: Optional[str] = None,
        n: Optional[int] = None,
        service_tier: Optional[Literal["auto", "on_demand", "flex", "performance"]] = None,
        reasoning_effort: Optional[Literal["none", "default", "low", "medium", "high"]] = None,
        reasoning_format: Optional[Literal["hidden", "raw", "parsed"]] = None,
        include_reasoning: Optional[bool] = None,
        documents: Optional[List[Document]] = None,
        enable_citations: Optional[bool] = None,
        search_settings: Optional[SearchSettings] = None,
        compound_custom: Optional[Dict[str, Any]] = None,
        disable_tool_validation: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Construye el body de la request según el esquema de Groq"""

        # Validaciones
        if tools and len(tools) > 128:
            raise ValueError("Groq soporta máximo 128 herramientas")

        if stop:
            stop_list = [stop] if isinstance(stop, str) else stop
            if len(stop_list) > 4:
                raise ValueError("Groq soporta máximo 4 secuencias de parada")

        if reasoning_format and include_reasoning:
            raise ValueError("reasoning_format e include_reasoning son mutuamente exclusivos")

        body: Dict[str, Any] = {
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    **({k: v for k, v in {
                        "name": msg.name,
                        "tool_calls": msg.tool_calls,
                        "tool_call_id": msg.tool_call_id
                    }.items() if v is not None})
                }
                for msg in messages
            ],
            "model": model,
        }

        # Parámetros opcionales
        if temperature is not None:
            body["temperature"] = temperature

        if max_completion_tokens is not None:
            body["max_completion_tokens"] = max_completion_tokens

        if stream:
            body["stream"] = stream

        if stream_options is not None:
            body["stream_options"] = stream_options

        if stop is not None:
            body["stop"] = stop

        if top_p is not None:
            body["top_p"] = top_p

        if tools is not None:
            body["tools"] = [
                {
                    "type": tool.type,
                    "function": {
                        "name": tool.function.name,
                        "description": tool.function.description,
                        "parameters": tool.function.parameters
                    }
                }
                for tool in tools
            ]

        if tool_choice is not None:
            body["tool_choice"] = tool_choice

        if parallel_tool_calls is not None:
            body["parallel_tool_calls"] = parallel_tool_calls

        if response_format is not None:
            body["response_format"] = response_format

        if seed is not None:
            body["seed"] = seed

        if user is not None:
            body["user"] = user

        if n is not None:
            body["n"] = n

        if service_tier is not None:
            body["service_tier"] = service_tier

        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort

        if reasoning_format is not None:
            body["reasoning_format"] = reasoning_format

        if include_reasoning is not None:
            body["include_reasoning"] = include_reasoning

        if documents is not None:
            body["documents"] = [
                {
                    "text": doc.text,
                    **({k: v for k, v in {"id": doc.id}.items() if v is not None})
                }
                for doc in documents
            ]

        if enable_citations is not None:
            body["enable_citations"] = enable_citations

        if search_settings is not None:
            body["search_settings"] = {
                k: v for k, v in {
                    "exclude_domains": search_settings.exclude_domains,
                    "include_domains": search_settings.include_domains
                }.items() if v is not None
            }

        if compound_custom is not None:
            body["compound_custom"] = compound_custom

        if disable_tool_validation is not None:
            body["disable_tool_validation"] = disable_tool_validation

        return body

    def _parse_response(self, response_data: Dict[str, Any]) -> GroqResponse:
        """Parsea la respuesta JSON a un objeto tipado"""

        # Parsear choices
        choices = []
        for choice_data in response_data.get("choices", []):
            # Parsear mensaje
            msg_data = choice_data["message"]

            # Parsear tool_calls si existen
            tool_calls = None
            if "tool_calls" in msg_data and msg_data["tool_calls"]:
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        type=tc["type"],
                        function=FunctionCall(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"]
                        )
                    )
                    for tc in msg_data["tool_calls"]
                ]

            message = ResponseMessage(
                role=msg_data["role"],
                content=msg_data.get("content"),
                tool_calls=tool_calls,
                refusal=msg_data.get("refusal")
            )

            choice = Choice(
                index=choice_data["index"],
                message=message,
                finish_reason=choice_data["finish_reason"],
                logprobs=choice_data.get("logprobs")
            )
            choices.append(choice)

        # Parsear usage
        usage_data = response_data["usage"]
        usage = Usage(
            prompt_tokens=usage_data["prompt_tokens"],
            completion_tokens=usage_data["completion_tokens"],
            total_tokens=usage_data["total_tokens"],
            prompt_time=usage_data.get("prompt_time"),
            completion_time=usage_data.get("completion_time"),
            total_time=usage_data.get("total_time")
        )

        return GroqResponse(
            id=response_data["id"],
            object=response_data["object"],
            created=response_data["created"],
            model=response_data["model"],
            choices=choices,
            usage=usage,
            system_fingerprint=response_data.get("system_fingerprint"),
            usage_breakdown=response_data.get("usage_breakdown")
        )

    def create_chat_completion(
        self,
        messages: List[Message],
        model: str,
        temperature: Optional[float] = None,
        max_completion_tokens: Optional[int] = None,
        stream: bool = False,
        stream_options: Optional[Dict[str, Any]] = None,
        stop: Optional[Union[str, List[str]]] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        parallel_tool_calls: Optional[bool] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        user: Optional[str] = None,
        n: Optional[int] = None,
        service_tier: Optional[Literal["auto", "on_demand", "flex", "performance"]] = None,
        reasoning_effort: Optional[Literal["none", "default", "low", "medium", "high"]] = None,
        reasoning_format: Optional[Literal["hidden", "raw", "parsed"]] = None,
        include_reasoning: Optional[bool] = None,
        documents: Optional[List[Document]] = None,
        enable_citations: Optional[bool] = None,
        search_settings: Optional[SearchSettings] = None,
        compound_custom: Optional[Dict[str, Any]] = None,
        disable_tool_validation: Optional[bool] = None,
    ) -> GroqResponse:
        """
        Crea una chat completion usando la API de Groq.

        Args:
            messages: Lista de mensajes de la conversación
            model: ID del modelo (ej: "llama-3.3-70b-versatile")
            temperature: Control de aleatoriedad (0-2). Por defecto 1
            max_completion_tokens: Número máximo de tokens a generar
            stream: Si usar streaming (solo para validación, usar create_chat_completion_stream)
            stream_options: Opciones de streaming (ej: {"include_usage": true})
            stop: Hasta 4 secuencias de parada (string o array)
            top_p: Muestreo nucleus (0-1). Por defecto 1
            tools: Lista de herramientas disponibles (máximo 128)
            tool_choice: Control de uso de herramientas ("none", "auto", "required", o específico)
            parallel_tool_calls: Habilitar llamadas paralelas a herramientas
            response_format: Formato de respuesta (json_schema, json_object, text)
            seed: Semilla para muestreo determinístico (mejor esfuerzo)
            user: Identificador único del usuario final
            n: Número de completions a generar (actualmente solo soporta 1)
            service_tier: Nivel de servicio ("auto", "on_demand", "flex", "performance")
            reasoning_effort: Esfuerzo de razonamiento ("none", "default", "low", "medium", "high")
            reasoning_format: Formato de tokens de razonamiento ("hidden", "raw", "parsed")
            include_reasoning: Si incluir campo reasoning (mutuamente exclusivo con reasoning_format)
            documents: Lista de documentos para contexto
            enable_citations: Habilitar citaciones en la respuesta
            search_settings: Configuración de búsqueda web
            compound_custom: Configuración personalizada para Compound AI
            disable_tool_validation: Deshabilitar validación de herramientas

        Returns:
            GroqResponse con la respuesta del modelo

        Raises:
            httpx.HTTPStatusError: Si la API devuelve un error HTTP
            ValueError: Si los parámetros son inválidos

        Example:
            >>> client = GroqClient(api_key="gsk_...")
            >>> response = client.create_chat_completion(
            ...     messages=[Message(role="user", content="Hello!")],
            ...     model="llama-3.3-70b-versatile",
            ...     temperature=0.7
            ... )
            >>> print(response.choices[0].message.content)
        """

        headers = self._build_headers()
        body = self._build_request_body(
            messages=messages,
            model=model,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            stream=stream,
            stream_options=stream_options,
            stop=stop,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=response_format,
            seed=seed,
            user=user,
            n=n,
            service_tier=service_tier,
            reasoning_effort=reasoning_effort,
            reasoning_format=reasoning_format,
            include_reasoning=include_reasoning,
            documents=documents,
            enable_citations=enable_citations,
            search_settings=search_settings,
            compound_custom=compound_custom,
            disable_tool_validation=disable_tool_validation,
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
                    error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                except:
                    error_msg = f"HTTP {response.status_code}: {response.text}"

                raise httpx.HTTPStatusError(
                    f"Groq API error: {error_msg}",
                    request=response.request,
                    response=response
                )

            response_data = response.json()
            return self._parse_response(response_data)

    def create_chat_completion_stream(
        self,
        messages: List[Message],
        model: str,
        temperature: Optional[float] = None,
        max_completion_tokens: Optional[int] = None,
        stream_options: Optional[Dict[str, Any]] = None,
        stop: Optional[Union[str, List[str]]] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        parallel_tool_calls: Optional[bool] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        user: Optional[str] = None,
        n: Optional[int] = None,
        service_tier: Optional[Literal["auto", "on_demand", "flex", "performance"]] = None,
        reasoning_effort: Optional[Literal["none", "default", "low", "medium", "high"]] = None,
        reasoning_format: Optional[Literal["hidden", "raw", "parsed"]] = None,
        include_reasoning: Optional[bool] = None,
        documents: Optional[List[Document]] = None,
        enable_citations: Optional[bool] = None,
        search_settings: Optional[SearchSettings] = None,
        compound_custom: Optional[Dict[str, Any]] = None,
        disable_tool_validation: Optional[bool] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Crea una chat completion con streaming (server-sent events).

        Args:
            messages: Lista de mensajes de la conversación
            model: ID del modelo
            temperature: Control de aleatoriedad (0-2)
            max_completion_tokens: Número máximo de tokens a generar
            stream_options: Opciones de streaming (ej: {"include_usage": true})
            stop: Hasta 4 secuencias de parada
            top_p: Muestreo nucleus (0-1)
            tools: Lista de herramientas disponibles (máximo 128)
            tool_choice: Control de uso de herramientas
            parallel_tool_calls: Habilitar llamadas paralelas a herramientas
            response_format: Formato de respuesta
            seed: Semilla para muestreo determinístico
            user: Identificador del usuario final
            n: Número de completions (actualmente solo soporta 1)
            service_tier: Nivel de servicio
            reasoning_effort: Esfuerzo de razonamiento
            reasoning_format: Formato de tokens de razonamiento
            include_reasoning: Si incluir campo reasoning
            documents: Lista de documentos para contexto
            enable_citations: Habilitar citaciones
            search_settings: Configuración de búsqueda web
            compound_custom: Configuración para Compound AI
            disable_tool_validation: Deshabilitar validación de herramientas

        Yields:
            Dict con eventos de streaming (object: "chat.completion.chunk")
            El evento final es "data: [DONE]"

        Example:
            >>> client = GroqClient(api_key="gsk_...")
            >>> for chunk in client.create_chat_completion_stream(
            ...     messages=[Message(role="user", content="Hello!")],
            ...     model="llama-3.3-70b-versatile"
            ... ):
            ...     if chunk.get("choices"):
            ...         delta = chunk["choices"][0].get("delta", {})
            ...         if "content" in delta:
            ...             print(delta["content"], end="")
        """

        headers = self._build_headers()
        body = self._build_request_body(
            messages=messages,
            model=model,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            stream=True,
            stream_options=stream_options,
            stop=stop,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=response_format,
            seed=seed,
            user=user,
            n=n,
            service_tier=service_tier,
            reasoning_effort=reasoning_effort,
            reasoning_format=reasoning_format,
            include_reasoning=include_reasoning,
            documents=documents,
            enable_citations=enable_citations,
            search_settings=search_settings,
            compound_custom=compound_custom,
            disable_tool_validation=disable_tool_validation,
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

def fetch_groq(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    temperature: Optional[float] = None,
    max_completion_tokens: Optional[int] = None,
    stream_options: Optional[Dict[str, Any]] = None,
    stop: Optional[Union[str, List[str]]] = None,
    top_p: Optional[float] = None,
    tools: Optional[List[Tool]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    parallel_tool_calls: Optional[bool] = None,
    response_format: Optional[Dict[str, Any]] = None,
    seed: Optional[int] = None,
    user: Optional[str] = None,
    n: Optional[int] = None,
    service_tier: Optional[Literal["auto", "on_demand", "flex", "performance"]] = None,
    reasoning_effort: Optional[Literal["none", "default", "low", "medium", "high"]] = None,
    reasoning_format: Optional[Literal["hidden", "raw", "parsed"]] = None,
    include_reasoning: Optional[bool] = None,
    documents: Optional[List[Document]] = None,
    enable_citations: Optional[bool] = None,
    search_settings: Optional[SearchSettings] = None,
    compound_custom: Optional[Dict[str, Any]] = None,
    disable_tool_validation: Optional[bool] = None,
) -> Union[GroqResponse, Iterator[Dict[str, Any]]]:
    """
    Función de conveniencia para hacer requests a Groq API.

    Args:
        api_key: API key de Groq
        messages: Lista de mensajes de la conversación
        model: ID del modelo a usar
        stream: Si usar streaming o no
        temperature: Control de aleatoriedad (0-2)
        max_completion_tokens: Número máximo de tokens a generar
        stream_options: Opciones de streaming
        stop: Secuencias de parada (máximo 4)
        top_p: Muestreo nucleus (0-1)
        tools: Lista de herramientas (máximo 128)
        tool_choice: Control de uso de herramientas
        parallel_tool_calls: Habilitar llamadas paralelas
        response_format: Formato de respuesta
        seed: Semilla para determinismo
        user: Identificador del usuario
        n: Número de completions (solo soporta 1)
        service_tier: Nivel de servicio
        reasoning_effort: Esfuerzo de razonamiento
        reasoning_format: Formato de razonamiento
        include_reasoning: Incluir razonamiento
        documents: Documentos para contexto
        enable_citations: Habilitar citaciones
        search_settings: Configuración de búsqueda
        compound_custom: Configuración Compound AI
        disable_tool_validation: Deshabilitar validación de tools

    Returns:
        GroqResponse si stream=False
        Iterator[Dict] si stream=True

    Example:
        >>> from fetchers.groq import fetch_groq, Message
        >>>
        >>> response = fetch_groq(
        ...     api_key="gsk_...",
        ...     model="llama-3.3-70b-versatile",
        ...     messages=[
        ...         Message(role="user", content="Hello, Groq!")
        ...     ],
        ...     temperature=0.7,
        ...     max_completion_tokens=1024
        ... )
        >>> print(response.choices[0].message.content)
    """

    client = GroqClient(api_key=api_key)

    if stream:
        return client.create_chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            stream_options=stream_options,
            stop=stop,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=response_format,
            seed=seed,
            user=user,
            n=n,
            service_tier=service_tier,
            reasoning_effort=reasoning_effort,
            reasoning_format=reasoning_format,
            include_reasoning=include_reasoning,
            documents=documents,
            enable_citations=enable_citations,
            search_settings=search_settings,
            compound_custom=compound_custom,
            disable_tool_validation=disable_tool_validation,
        )
    else:
        return client.create_chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            stream=False,
            stream_options=stream_options,
            stop=stop,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=response_format,
            seed=seed,
            user=user,
            n=n,
            service_tier=service_tier,
            reasoning_effort=reasoning_effort,
            reasoning_format=reasoning_format,
            include_reasoning=include_reasoning,
            documents=documents,
            enable_citations=enable_citations,
            search_settings=search_settings,
            compound_custom=compound_custom,
            disable_tool_validation=disable_tool_validation,
        )
