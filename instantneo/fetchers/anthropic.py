"""
Fetcher para Anthropic Claude API.

Basado en la documentación oficial de /v1/messages endpoint.
"""

from typing import Any, Dict, List, Optional, Union, Literal, Iterator
import httpx
import json

# Importar modelos de datos desde el módulo separado
from models.anthropic import (
    MessageContent,
    Message,
    Tool,
    CacheControl,
    ContentBlock,
    Usage,
    AnthropicResponse,
    AnthropicError
)


# ============================================================================
# CLIENTE PRINCIPAL
# ============================================================================

class AnthropicClient:
    """Cliente HTTP para Anthropic Claude API"""

    BASE_URL = "https://api.anthropic.com/v1/messages"
    DEFAULT_TIMEOUT = 60.0

    def __init__(
        self,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 2
    ):
        """
        Inicializa el cliente de Anthropic.

        Args:
            api_key: API key de Anthropic
            timeout: Timeout en segundos para las requests
            max_retries: Número máximo de reintentos en caso de error
        """
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    def _build_headers(self, anthropic_version: str = "2023-06-01") -> Dict[str, str]:
        """Construye los headers necesarios para la API"""
        return {
            "x-api-key": self.api_key,
            "anthropic-version": anthropic_version,
            "content-type": "application/json",
        }

    def _build_request_body(
        self,
        model: str,
        messages: List[Message],
        max_tokens: int,
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        temperature: Optional[float] = None,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        thinking: Optional[Dict[str, Any]] = None,
        container: Optional[str] = None,
        context_management: Optional[Dict[str, Any]] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        service_tier: Optional[Literal["auto", "standard_only"]] = None,
    ) -> Dict[str, Any]:
        """Construye el body de la request según el esquema de Anthropic"""

        body: Dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content
                }
                for msg in messages
            ],
            "max_tokens": max_tokens,
        }

        # Parámetros opcionales
        if system is not None:
            body["system"] = system

        if temperature is not None:
            body["temperature"] = temperature

        if top_k is not None:
            body["top_k"] = top_k

        if top_p is not None:
            body["top_p"] = top_p

        if stop_sequences is not None:
            body["stop_sequences"] = stop_sequences

        if stream:
            body["stream"] = stream

        if metadata is not None:
            body["metadata"] = metadata

        if tools is not None:
            body["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema
                }
                for tool in tools
            ]

        if tool_choice is not None:
            body["tool_choice"] = tool_choice

        if thinking is not None:
            body["thinking"] = thinking

        if container is not None:
            body["container"] = container

        if context_management is not None:
            body["context_management"] = context_management

        if mcp_servers is not None:
            body["mcp_servers"] = mcp_servers

        if service_tier is not None:
            body["service_tier"] = service_tier

        return body

    def _parse_response(self, response_data: Dict[str, Any]) -> AnthropicResponse:
        """Parsea la respuesta JSON a un objeto tipado"""

        # Parsear bloques de contenido
        content_blocks = []
        for block in response_data.get("content", []):
            content_blocks.append(ContentBlock(
                type=block["type"],
                text=block.get("text"),
                thinking=block.get("thinking"),
                id=block.get("id"),
                name=block.get("name"),
                input=block.get("input")
            ))

        # Parsear usage
        usage_data = response_data["usage"]
        usage = Usage(
            input_tokens=usage_data["input_tokens"],
            output_tokens=usage_data["output_tokens"],
            cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens"),
            cache_read_input_tokens=usage_data.get("cache_read_input_tokens")
        )

        return AnthropicResponse(
            id=response_data["id"],
            type=response_data["type"],
            role=response_data["role"],
            content=content_blocks,
            model=response_data["model"],
            stop_reason=response_data.get("stop_reason"),
            stop_sequence=response_data.get("stop_sequence"),
            usage=usage,
            context_management=response_data.get("context_management"),
            container=response_data.get("container")
        )

    def create_message(
        self,
        model: str,
        messages: List[Message],
        max_tokens: int,
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        temperature: Optional[float] = None,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        thinking: Optional[Dict[str, Any]] = None,
        container: Optional[str] = None,
        context_management: Optional[Dict[str, Any]] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        service_tier: Optional[Literal["auto", "standard_only"]] = None,
    ) -> AnthropicResponse:
        """
        Crea un mensaje (completion) usando la API de Anthropic.

        Args:
            model: ID del modelo (ej: "claude-sonnet-4-5-20250929")
            messages: Lista de mensajes de la conversación
            max_tokens: Número máximo de tokens a generar
            system: Prompt de sistema (string o lista de bloques)
            temperature: Control de aleatoriedad (0-1)
            top_k: Muestreo top-k
            top_p: Muestreo nucleus (0-1)
            stop_sequences: Secuencias de parada personalizadas
            stream: Si usar streaming (solo para validación, usar create_message_stream)
            metadata: Metadatos adicionales
            tools: Lista de herramientas disponibles
            tool_choice: Control de uso de herramientas
            thinking: Configuración de pensamiento extendido
            container: Identificador de contenedor
            context_management: Configuración de gestión de contexto
            mcp_servers: Servidores MCP
            service_tier: Nivel de servicio ("auto" o "standard_only")

        Returns:
            AnthropicResponse con la respuesta del modelo

        Raises:
            httpx.HTTPStatusError: Si la API devuelve un error HTTP
            ValueError: Si los parámetros son inválidos
        """

        headers = self._build_headers()
        body = self._build_request_body(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            stop_sequences=stop_sequences,
            stream=stream,
            metadata=metadata,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
            container=container,
            context_management=context_management,
            mcp_servers=mcp_servers,
            service_tier=service_tier,
        )

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                self.BASE_URL,
                headers=headers,
                json=body
            )

            # Manejar errores HTTP
            if response.status_code != 200:
                error_data = response.json()
                raise httpx.HTTPStatusError(
                    f"Anthropic API error: {error_data.get('error', {}).get('message', 'Unknown error')}",
                    request=response.request,
                    response=response
                )

            response_data = response.json()
            return self._parse_response(response_data)

    def create_message_stream(
        self,
        model: str,
        messages: List[Message],
        max_tokens: int,
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        temperature: Optional[float] = None,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        thinking: Optional[Dict[str, Any]] = None,
        container: Optional[str] = None,
        context_management: Optional[Dict[str, Any]] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        service_tier: Optional[Literal["auto", "standard_only"]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Crea un mensaje con streaming (server-sent events).

        Args:
            model: ID del modelo
            messages: Lista de mensajes de la conversación
            max_tokens: Número máximo de tokens a generar
            system: Prompt de sistema (string o lista de bloques)
            temperature: Control de aleatoriedad (0-1)
            top_k: Muestreo top-k
            top_p: Muestreo nucleus (0-1)
            stop_sequences: Secuencias de parada personalizadas
            metadata: Metadatos adicionales
            tools: Lista de herramientas disponibles
            tool_choice: Control de uso de herramientas
            thinking: Configuración de pensamiento extendido
            container: Identificador de contenedor
            context_management: Configuración de gestión de contexto
            mcp_servers: Servidores MCP
            service_tier: Nivel de servicio ("auto" o "standard_only")

        Yields:
            Dict con eventos de streaming
        """

        headers = self._build_headers()
        body = self._build_request_body(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            stop_sequences=stop_sequences,
            stream=True,
            metadata=metadata,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
            container=container,
            context_management=context_management,
            mcp_servers=mcp_servers,
            service_tier=service_tier,
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

def fetch_anthropic(
    api_key: str,
    model: str,
    messages: List[Message],
    max_tokens: int,
    stream: bool = False,
    system: Optional[Union[str, List[Dict[str, Any]]]] = None,
    temperature: Optional[float] = None,
    top_k: Optional[int] = None,
    top_p: Optional[float] = None,
    stop_sequences: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Tool]] = None,
    tool_choice: Optional[Dict[str, Any]] = None,
    thinking: Optional[Dict[str, Any]] = None,
    container: Optional[str] = None,
    context_management: Optional[Dict[str, Any]] = None,
    mcp_servers: Optional[List[Dict[str, Any]]] = None,
    service_tier: Optional[Literal["auto", "standard_only"]] = None,
) -> Union[AnthropicResponse, Iterator[Dict[str, Any]]]:
    """
    Función de conveniencia para hacer requests a Anthropic Claude API.

    Args:
        api_key: API key de Anthropic
        model: ID del modelo a usar
        messages: Lista de mensajes de la conversación
        max_tokens: Número máximo de tokens a generar
        stream: Si usar streaming o no
        system: Prompt de sistema (string o lista de bloques)
        temperature: Control de aleatoriedad (0-1)
        top_k: Muestreo top-k
        top_p: Muestreo nucleus (0-1)
        stop_sequences: Secuencias de parada personalizadas
        metadata: Metadatos adicionales
        tools: Lista de herramientas disponibles
        tool_choice: Control de uso de herramientas
        thinking: Configuración de pensamiento extendido
        container: Identificador de contenedor
        context_management: Configuración de gestión de contexto
        mcp_servers: Servidores MCP
        service_tier: Nivel de servicio ("auto" o "standard_only")

    Returns:
        AnthropicResponse si stream=False
        Iterator[Dict] si stream=True

    Example:
        >>> from fetchers.anthropic import fetch_anthropic, Message
        >>>
        >>> response = fetch_anthropic(
        ...     api_key="sk-ant-...",
        ...     model="claude-sonnet-4-5-20250929",
        ...     messages=[
        ...         Message(role="user", content="Hello, Claude!")
        ...     ],
        ...     max_tokens=1024,
        ...     temperature=0.7
        ... )
        >>> print(response.content[0].text)
    """

    client = AnthropicClient(api_key=api_key)

    if stream:
        return client.create_message_stream(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            stop_sequences=stop_sequences,
            metadata=metadata,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
            container=container,
            context_management=context_management,
            mcp_servers=mcp_servers,
            service_tier=service_tier,
        )
    else:
        return client.create_message(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            stop_sequences=stop_sequences,
            stream=False,
            metadata=metadata,
            tools=tools,
            tool_choice=tool_choice,
            thinking=thinking,
            container=container,
            context_management=context_management,
            mcp_servers=mcp_servers,
            service_tier=service_tier,
        )
