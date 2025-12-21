"""
Fetcher para Google Gemini API (ai.google.dev).

Cliente HTTP puro para el endpoint generateContent de Gemini.
Usa API Key para autenticación.
"""

from typing import Any, Dict, List, Optional, Iterator
import httpx
import json

from instantneo.models.gemini import (
    Part,
    Content,
    FunctionDeclaration,
    GenerationConfig,
    SafetySetting,
    Candidate,
    UsageMetadata,
    SafetyRating,
    GeminiResponse,
    GeminiError,
)


# ============================================================================
# CLIENTE PRINCIPAL
# ============================================================================

class GeminiClient:
    """Cliente HTTP para Google Gemini API"""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    DEFAULT_TIMEOUT = 60.0

    def __init__(
        self,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Inicializa el cliente de Gemini.

        Args:
            api_key: API key de Google AI Studio
            timeout: Timeout en segundos para las requests
        """
        self.api_key = api_key
        self.timeout = timeout

    def _build_headers(self) -> Dict[str, str]:
        """Construye los headers necesarios para la API."""
        return {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def _get_endpoint(self, model: str, stream: bool = False) -> str:
        """Construye la URL del endpoint."""
        action = "streamGenerateContent" if stream else "generateContent"
        url = f"{self.BASE_URL}/models/{model}:{action}"
        if stream:
            url += "?alt=sse"
        return url

    def _build_request_body(
        self,
        contents: List[Content],
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None,
        tools: Optional[List[FunctionDeclaration]] = None,
        tool_config: Optional[Dict[str, Any]] = None,
        safety_settings: Optional[List[SafetySetting]] = None,
    ) -> Dict[str, Any]:
        """Construye el body de la request."""

        body: Dict[str, Any] = {
            "contents": [
                {
                    "role": content.role,
                    "parts": [self._part_to_dict(part) for part in content.parts]
                }
                for content in contents
            ]
        }

        # System instruction
        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # Generation config
        if generation_config:
            config = {}
            if generation_config.temperature is not None:
                config["temperature"] = generation_config.temperature
            if generation_config.top_p is not None:
                config["topP"] = generation_config.top_p
            if generation_config.top_k is not None:
                config["topK"] = generation_config.top_k
            if generation_config.max_output_tokens is not None:
                config["maxOutputTokens"] = generation_config.max_output_tokens
            if generation_config.stop_sequences:
                config["stopSequences"] = generation_config.stop_sequences
            if generation_config.response_mime_type:
                config["responseMimeType"] = generation_config.response_mime_type
            if config:
                body["generationConfig"] = config

        # Tools
        if tools:
            body["tools"] = [{
                "functionDeclarations": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    }
                    for tool in tools
                ]
            }]

        # Tool config
        if tool_config:
            body["toolConfig"] = tool_config

        # Safety settings
        if safety_settings:
            body["safetySettings"] = [
                {
                    "category": setting.category,
                    "threshold": setting.threshold,
                }
                for setting in safety_settings
            ]

        return body

    def _part_to_dict(self, part: Part) -> Dict[str, Any]:
        """Convierte un Part a diccionario para JSON."""
        if part.text is not None:
            return {"text": part.text}
        elif part.inline_data is not None:
            return {"inlineData": part.inline_data}
        elif part.file_data is not None:
            return {"fileData": part.file_data}
        elif part.function_call is not None:
            return {"functionCall": part.function_call}
        elif part.function_response is not None:
            return {"functionResponse": part.function_response}
        return {}

    def _parse_response(self, response_data: Dict[str, Any]) -> GeminiResponse:
        """Parsea la respuesta JSON a un objeto tipado."""

        candidates = []
        for cand in response_data.get("candidates", []):
            # Parsear content
            content_data = cand.get("content", {})
            parts = []
            for part_data in content_data.get("parts", []):
                parts.append(Part(
                    text=part_data.get("text"),
                    inline_data=part_data.get("inlineData"),
                    file_data=part_data.get("fileData"),
                    function_call=part_data.get("functionCall"),
                    function_response=part_data.get("functionResponse"),
                ))

            content = Content(
                role=content_data.get("role", "model"),
                parts=parts,
            )

            # Parsear safety ratings
            safety_ratings = None
            if "safetyRatings" in cand:
                safety_ratings = [
                    SafetyRating(
                        category=sr.get("category", ""),
                        probability=sr.get("probability", ""),
                        blocked=sr.get("blocked", False),
                    )
                    for sr in cand["safetyRatings"]
                ]

            candidates.append(Candidate(
                content=content,
                finish_reason=cand.get("finishReason", "STOP"),
                safety_ratings=safety_ratings,
            ))

        # Parsear usage metadata
        usage_data = response_data.get("usageMetadata", {})
        usage_metadata = UsageMetadata(
            prompt_token_count=usage_data.get("promptTokenCount", 0),
            candidates_token_count=usage_data.get("candidatesTokenCount", 0),
            total_token_count=usage_data.get("totalTokenCount", 0),
        )

        return GeminiResponse(
            candidates=candidates,
            usage_metadata=usage_metadata,
            model_version=response_data.get("modelVersion"),
        )

    def generate_content(
        self,
        model: str,
        contents: List[Content],
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None,
        tools: Optional[List[FunctionDeclaration]] = None,
        tool_config: Optional[Dict[str, Any]] = None,
        safety_settings: Optional[List[SafetySetting]] = None,
    ) -> GeminiResponse:
        """
        Genera contenido usando Gemini API.

        Args:
            model: ID del modelo (ej: "gemini-2.0-flash")
            contents: Lista de mensajes de la conversación
            generation_config: Configuración de generación
            system_instruction: Instrucciones del sistema
            tools: Lista de funciones disponibles
            tool_config: Configuración de uso de tools
            safety_settings: Configuración de filtros de seguridad

        Returns:
            GeminiResponse con la respuesta del modelo

        Raises:
            httpx.HTTPStatusError: Si la API devuelve un error HTTP
        """

        headers = self._build_headers()
        body = self._build_request_body(
            contents=contents,
            generation_config=generation_config,
            system_instruction=system_instruction,
            tools=tools,
            tool_config=tool_config,
            safety_settings=safety_settings,
        )

        endpoint = self._get_endpoint(model, stream=False)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(endpoint, headers=headers, json=body)

            if response.status_code != 200:
                error_data = response.json()
                error_info = error_data.get("error", {})
                raise httpx.HTTPStatusError(
                    f"Gemini API error: {error_info.get('message', 'Unknown error')}",
                    request=response.request,
                    response=response
                )

            response_data = response.json()
            return self._parse_response(response_data)

    def generate_content_stream(
        self,
        model: str,
        contents: List[Content],
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None,
        tools: Optional[List[FunctionDeclaration]] = None,
        tool_config: Optional[Dict[str, Any]] = None,
        safety_settings: Optional[List[SafetySetting]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Genera contenido con streaming.

        Args:
            model: ID del modelo
            contents: Lista de mensajes de la conversación
            generation_config: Configuración de generación
            system_instruction: Instrucciones del sistema
            tools: Lista de funciones disponibles
            tool_config: Configuración de uso de tools
            safety_settings: Configuración de filtros de seguridad

        Yields:
            Dict con cada chunk de la respuesta
        """

        headers = self._build_headers()
        body = self._build_request_body(
            contents=contents,
            generation_config=generation_config,
            system_instruction=system_instruction,
            tools=tools,
            tool_config=tool_config,
            safety_settings=safety_settings,
        )

        endpoint = self._get_endpoint(model, stream=True)

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", endpoint, headers=headers, json=body) as response:
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

def fetch_gemini(
    api_key: str,
    model: str,
    contents: List[Content],
    stream: bool = False,
    generation_config: Optional[GenerationConfig] = None,
    system_instruction: Optional[str] = None,
    tools: Optional[List[FunctionDeclaration]] = None,
    tool_config: Optional[Dict[str, Any]] = None,
    safety_settings: Optional[List[SafetySetting]] = None,
):
    """
    Función de conveniencia para hacer requests a Gemini API.

    Args:
        api_key: API key de Google AI Studio
        model: ID del modelo a usar
        contents: Lista de mensajes de la conversación
        stream: Si usar streaming o no
        generation_config: Configuración de generación
        system_instruction: Instrucciones del sistema
        tools: Lista de funciones disponibles
        tool_config: Configuración de uso de tools
        safety_settings: Configuración de filtros de seguridad

    Returns:
        GeminiResponse si stream=False
        Iterator[Dict] si stream=True

    Example:
        >>> from instantneo.fetchers.gemini import fetch_gemini, Content, Part
        >>>
        >>> response = fetch_gemini(
        ...     api_key="AI...",
        ...     model="gemini-2.0-flash",
        ...     contents=[
        ...         Content(role="user", parts=[Part(text="Hello!")])
        ...     ],
        ... )
        >>> print(response.candidates[0].content.parts[0].text)
    """

    client = GeminiClient(api_key=api_key)

    if stream:
        return client.generate_content_stream(
            model=model,
            contents=contents,
            generation_config=generation_config,
            system_instruction=system_instruction,
            tools=tools,
            tool_config=tool_config,
            safety_settings=safety_settings,
        )
    else:
        return client.generate_content(
            model=model,
            contents=contents,
            generation_config=generation_config,
            system_instruction=system_instruction,
            tools=tools,
            tool_config=tool_config,
            safety_settings=safety_settings,
        )
