"""
Fetcher para Cerebras API.

Basado en la API de Cerebras compatible con OpenAI Chat Completions.
Endpoint: https://api.cerebras.ai/v1/chat/completions
"""

from typing import Any, Dict, List, Optional, Union, Literal, Iterator
import httpx
import json

from instantneo.models.cerebras import (
    Message,
    Tool,
    ToolFunction,
    Prediction,
    FunctionCall,
    ToolCall,
    ResponseMessage,
    Choice,
    Usage,
    PromptTokensDetails,
    CompletionTokensDetails,
    TimeInfo,
    CerebrasResponse,
    CerebrasError,
)


# ============================================================================
# CLIENTE PRINCIPAL
# ============================================================================

class CerebrasClient:
    """Cliente HTTP para Cerebras API"""

    BASE_URL = "https://api.cerebras.ai/v1/chat/completions"
    DEFAULT_TIMEOUT = 600.0

    def __init__(
        self,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 2
    ):
        """
        Inicializa el cliente de Cerebras.

        Args:
            api_key: API key de Cerebras
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
        stop: Optional[Union[str, List[str]]] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        parallel_tool_calls: Optional[bool] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        user: Optional[str] = None,
        reasoning_effort: Optional[Literal["low", "medium", "high"]] = None,
        clear_thinking: Optional[bool] = None,
        prediction: Optional[Prediction] = None,
        service_tier: Optional[Literal["priority", "default", "auto", "flex"]] = None,
        logprobs: Optional[bool] = None,
        top_logprobs: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Construye el body de la request según el esquema de Cerebras"""

        # Validaciones
        if temperature is not None and (temperature < 0 or temperature > 1.5):
            raise ValueError("Cerebras soporta temperature entre 0 y 1.5")

        if stop:
            stop_list = [stop] if isinstance(stop, str) else stop
            if len(stop_list) > 4:
                raise ValueError("Cerebras soporta máximo 4 secuencias de parada")

        if top_logprobs is not None and (top_logprobs < 0 or top_logprobs > 20):
            raise ValueError("top_logprobs debe estar entre 0 y 20")

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

        # Parámetros específicos de Cerebras
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort

        if clear_thinking is not None:
            body["clear_thinking"] = clear_thinking

        if prediction is not None:
            body["prediction"] = {
                "type": prediction.type,
                "content": prediction.content,
            }

        if service_tier is not None:
            body["service_tier"] = service_tier

        if logprobs is not None:
            body["logprobs"] = logprobs

        if top_logprobs is not None:
            body["top_logprobs"] = top_logprobs

        return body

    def _parse_response(self, response_data: Dict[str, Any]) -> CerebrasResponse:
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
                refusal=msg_data.get("refusal"),
                reasoning=msg_data.get("reasoning"),
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

        prompt_tokens_details = None
        if "prompt_tokens_details" in usage_data and usage_data["prompt_tokens_details"]:
            ptd = usage_data["prompt_tokens_details"]
            prompt_tokens_details = PromptTokensDetails(
                cached_tokens=ptd.get("cached_tokens", 0)
            )

        completion_tokens_details = None
        if "completion_tokens_details" in usage_data and usage_data["completion_tokens_details"]:
            ctd = usage_data["completion_tokens_details"]
            completion_tokens_details = CompletionTokensDetails(
                accepted_prediction_tokens=ctd.get("accepted_prediction_tokens", 0),
                rejected_prediction_tokens=ctd.get("rejected_prediction_tokens", 0),
            )

        usage = Usage(
            prompt_tokens=usage_data["prompt_tokens"],
            completion_tokens=usage_data["completion_tokens"],
            total_tokens=usage_data["total_tokens"],
            prompt_tokens_details=prompt_tokens_details,
            completion_tokens_details=completion_tokens_details,
        )

        # Parsear time_info
        time_info = None
        if "time_info" in response_data and response_data["time_info"]:
            ti = response_data["time_info"]
            time_info = TimeInfo(
                queue_time=ti.get("queue_time"),
                prompt_time=ti.get("prompt_time"),
                completion_time=ti.get("completion_time"),
                total_time=ti.get("total_time"),
            )

        return CerebrasResponse(
            id=response_data["id"],
            object=response_data["object"],
            created=response_data["created"],
            model=response_data["model"],
            choices=choices,
            usage=usage,
            system_fingerprint=response_data.get("system_fingerprint"),
            time_info=time_info,
            service_tier_used=response_data.get("service_tier_used"),
        )

    def create_chat_completion(
        self,
        messages: List[Message],
        model: str,
        temperature: Optional[float] = None,
        max_completion_tokens: Optional[int] = None,
        stream: bool = False,
        stop: Optional[Union[str, List[str]]] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        parallel_tool_calls: Optional[bool] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        user: Optional[str] = None,
        reasoning_effort: Optional[Literal["low", "medium", "high"]] = None,
        clear_thinking: Optional[bool] = None,
        prediction: Optional[Prediction] = None,
        service_tier: Optional[Literal["priority", "default", "auto", "flex"]] = None,
        logprobs: Optional[bool] = None,
        top_logprobs: Optional[int] = None,
    ) -> CerebrasResponse:
        """
        Crea una chat completion usando la API de Cerebras.

        Args:
            messages: Lista de mensajes de la conversación
            model: ID del modelo (ej: "llama-3.3-70b", "llama-4-scout-17b-16e-instruct")
            temperature: Control de aleatoriedad (0-1.5). Por defecto 1
            max_completion_tokens: Número máximo de tokens a generar
            stream: Si usar streaming (solo para validación, usar create_chat_completion_stream)
            stop: Hasta 4 secuencias de parada (string o array)
            top_p: Muestreo nucleus (0-1). Por defecto 1
            tools: Lista de herramientas disponibles
            tool_choice: Control de uso de herramientas ("none", "auto", "required", o específico)
            parallel_tool_calls: Habilitar llamadas paralelas a herramientas
            response_format: Formato de respuesta (json_schema, json_object, text)
            seed: Semilla para muestreo determinístico
            user: Identificador único del usuario final
            reasoning_effort: Esfuerzo de razonamiento ("low", "medium", "high")
            clear_thinking: Habilitar clear thinking (razonamiento extendido)
            prediction: Contenido de predicción para speculative decoding
            service_tier: Nivel de servicio ("priority", "default", "auto", "flex")
            logprobs: Si incluir log probabilities
            top_logprobs: Número de top log probabilities por token (0-20)

        Returns:
            CerebrasResponse con la respuesta del modelo

        Raises:
            httpx.HTTPStatusError: Si la API devuelve un error HTTP
            ValueError: Si los parámetros son inválidos

        Example:
            >>> client = CerebrasClient(api_key="csk-...")
            >>> response = client.create_chat_completion(
            ...     messages=[Message(role="user", content="Hello!")],
            ...     model="llama-3.3-70b",
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
            stop=stop,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=response_format,
            seed=seed,
            user=user,
            reasoning_effort=reasoning_effort,
            clear_thinking=clear_thinking,
            prediction=prediction,
            service_tier=service_tier,
            logprobs=logprobs,
            top_logprobs=top_logprobs,
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
                except Exception:
                    error_msg = f"HTTP {response.status_code}: {response.text}"

                raise httpx.HTTPStatusError(
                    f"Cerebras API error: {error_msg}",
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
        stop: Optional[Union[str, List[str]]] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        parallel_tool_calls: Optional[bool] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        user: Optional[str] = None,
        reasoning_effort: Optional[Literal["low", "medium", "high"]] = None,
        clear_thinking: Optional[bool] = None,
        prediction: Optional[Prediction] = None,
        service_tier: Optional[Literal["priority", "default", "auto", "flex"]] = None,
        logprobs: Optional[bool] = None,
        top_logprobs: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Crea una chat completion con streaming (server-sent events).

        Args:
            messages: Lista de mensajes de la conversación
            model: ID del modelo
            temperature: Control de aleatoriedad (0-1.5)
            max_completion_tokens: Número máximo de tokens a generar
            stop: Hasta 4 secuencias de parada
            top_p: Muestreo nucleus (0-1)
            tools: Lista de herramientas disponibles
            tool_choice: Control de uso de herramientas
            parallel_tool_calls: Habilitar llamadas paralelas a herramientas
            response_format: Formato de respuesta
            seed: Semilla para muestreo determinístico
            user: Identificador del usuario final
            reasoning_effort: Esfuerzo de razonamiento
            clear_thinking: Habilitar clear thinking
            prediction: Contenido de predicción
            service_tier: Nivel de servicio
            logprobs: Si incluir log probabilities
            top_logprobs: Número de top log probabilities

        Yields:
            Dict con eventos de streaming (object: "chat.completion.chunk")
            El evento final es "data: [DONE]"

        Example:
            >>> client = CerebrasClient(api_key="csk-...")
            >>> for chunk in client.create_chat_completion_stream(
            ...     messages=[Message(role="user", content="Hello!")],
            ...     model="llama-3.3-70b"
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
            stop=stop,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=response_format,
            seed=seed,
            user=user,
            reasoning_effort=reasoning_effort,
            clear_thinking=clear_thinking,
            prediction=prediction,
            service_tier=service_tier,
            logprobs=logprobs,
            top_logprobs=top_logprobs,
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

def fetch_cerebras(
    api_key: str,
    messages: List[Message],
    model: str,
    stream: bool = False,
    temperature: Optional[float] = None,
    max_completion_tokens: Optional[int] = None,
    stop: Optional[Union[str, List[str]]] = None,
    top_p: Optional[float] = None,
    tools: Optional[List[Tool]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    parallel_tool_calls: Optional[bool] = None,
    response_format: Optional[Dict[str, Any]] = None,
    seed: Optional[int] = None,
    user: Optional[str] = None,
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = None,
    clear_thinking: Optional[bool] = None,
    prediction: Optional[Prediction] = None,
    service_tier: Optional[Literal["priority", "default", "auto", "flex"]] = None,
    logprobs: Optional[bool] = None,
    top_logprobs: Optional[int] = None,
) -> Union[CerebrasResponse, Iterator[Dict[str, Any]]]:
    """
    Función de conveniencia para hacer requests a Cerebras API.

    Args:
        api_key: API key de Cerebras
        messages: Lista de mensajes de la conversación
        model: ID del modelo a usar
        stream: Si usar streaming o no
        temperature: Control de aleatoriedad (0-1.5)
        max_completion_tokens: Número máximo de tokens a generar
        stop: Secuencias de parada (máximo 4)
        top_p: Muestreo nucleus (0-1)
        tools: Lista de herramientas
        tool_choice: Control de uso de herramientas
        parallel_tool_calls: Habilitar llamadas paralelas
        response_format: Formato de respuesta
        seed: Semilla para determinismo
        user: Identificador del usuario
        reasoning_effort: Esfuerzo de razonamiento
        clear_thinking: Habilitar clear thinking
        prediction: Contenido de predicción
        service_tier: Nivel de servicio
        logprobs: Si incluir log probabilities
        top_logprobs: Número de top log probabilities

    Returns:
        CerebrasResponse si stream=False
        Iterator[Dict] si stream=True

    Example:
        >>> from fetchers.cerebras import fetch_cerebras, Message
        >>>
        >>> response = fetch_cerebras(
        ...     api_key="csk-...",
        ...     model="llama-3.3-70b",
        ...     messages=[
        ...         Message(role="user", content="Hello, Cerebras!")
        ...     ],
        ...     temperature=0.7,
        ...     max_completion_tokens=1024
        ... )
        >>> print(response.choices[0].message.content)
    """

    client = CerebrasClient(api_key=api_key)

    if stream:
        return client.create_chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            stop=stop,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=response_format,
            seed=seed,
            user=user,
            reasoning_effort=reasoning_effort,
            clear_thinking=clear_thinking,
            prediction=prediction,
            service_tier=service_tier,
            logprobs=logprobs,
            top_logprobs=top_logprobs,
        )
    else:
        return client.create_chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            stream=False,
            stop=stop,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            response_format=response_format,
            seed=seed,
            user=user,
            reasoning_effort=reasoning_effort,
            clear_thinking=clear_thinking,
            prediction=prediction,
            service_tier=service_tier,
            logprobs=logprobs,
            top_logprobs=top_logprobs,
        )
