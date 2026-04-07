"""
Fetcher para Vertex AI Gemini API (Google Cloud).

Cliente HTTP para el endpoint generateContent de Gemini en Vertex AI.

Autenticación soportada:
- Service Account JSON (archivo o dict) - Recomendado
- Access Token directo (para casos especiales)

Requiere 'cryptography' para firmar JWTs con Service Account:
    pip install cryptography
"""

from typing import Any, Dict, List, Optional, Iterator, Union
import httpx
import json
import time
import base64

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
)


# ============================================================================
# UTILIDADES JWT / OAUTH
# ============================================================================

def _b64_encode(data: bytes) -> str:
    """Base64 URL-safe encoding sin padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _create_jwt(
    client_email: str,
    private_key: str,
    scope: str = "https://www.googleapis.com/auth/cloud-platform",
    token_uri: str = "https://oauth2.googleapis.com/token",
    lifetime_seconds: int = 3600,
) -> str:
    """
    Crea un JWT firmado para autenticación con Google OAuth.

    Args:
        client_email: Email del service account
        private_key: Clave privada RSA en formato PEM
        scope: Scope de OAuth requerido
        token_uri: URL del servidor de tokens
        lifetime_seconds: Tiempo de vida del JWT

    Returns:
        JWT firmado como string
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        raise ImportError(
            "El paquete 'cryptography' es requerido para autenticación con Service Account. "
            "Instálalo con: pip install cryptography"
        )

    now = int(time.time())

    # Header
    header = {"alg": "RS256", "typ": "JWT"}
    header_b64 = _b64_encode(json.dumps(header, separators=(",", ":")).encode())

    # Payload
    payload = {
        "iss": client_email,
        "scope": scope,
        "aud": token_uri,
        "iat": now,
        "exp": now + lifetime_seconds,
    }
    payload_b64 = _b64_encode(json.dumps(payload, separators=(",", ":")).encode())

    # Mensaje a firmar
    message = f"{header_b64}.{payload_b64}".encode()

    # Cargar clave privada y firmar
    private_key_bytes = private_key.encode() if isinstance(private_key, str) else private_key
    key = serialization.load_pem_private_key(
        private_key_bytes,
        password=None,
        backend=default_backend()
    )

    signature = key.sign(
        message,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    signature_b64 = _b64_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def _exchange_jwt_for_token(jwt: str, token_uri: str = "https://oauth2.googleapis.com/token") -> dict:
    """
    Intercambia un JWT firmado por un access token.

    Args:
        jwt: JWT firmado
        token_uri: URL del servidor de tokens

    Returns:
        Dict con access_token, expires_in, token_type
    """
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            error_data = response.json()
            raise RuntimeError(
                f"Error obteniendo access token: {error_data.get('error_description', error_data)}"
            )

        return response.json()


def _load_service_account(
    service_account_file: Optional[str] = None,
    service_account_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Carga la información del service account desde archivo o dict.

    Args:
        service_account_file: Ruta al archivo JSON
        service_account_info: Dict con la información del SA

    Returns:
        Dict con client_email, private_key, token_uri, project_id
    """
    if service_account_info:
        sa_info = service_account_info
    elif service_account_file:
        with open(service_account_file, "r") as f:
            sa_info = json.load(f)
    else:
        raise ValueError(
            "Debe proporcionar service_account_file o service_account_info"
        )

    required_fields = ["client_email", "private_key"]
    for field in required_fields:
        if field not in sa_info:
            raise ValueError(f"Campo requerido faltante en service account: {field}")

    return {
        "client_email": sa_info["client_email"],
        "private_key": sa_info["private_key"],
        "token_uri": sa_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        "project_id": sa_info.get("project_id"),
    }


# ============================================================================
# CLIENTE PRINCIPAL
# ============================================================================

class VertexAIClient:
    """
    Cliente HTTP para Vertex AI Gemini API.

    Autenticación:
    - Service Account (recomendado): Usa service_account_file o service_account_info
    - Access Token directo: Usa access_token (para casos especiales)

    Ejemplo con Service Account:
        client = VertexAIClient(
            location="us-central1",
            service_account_file="path/to/key.json"
        )

    Ejemplo con Access Token:
        client = VertexAIClient(
            location="us-central1",
            access_token="ya29..."
        )
    """

    DEFAULT_TIMEOUT = 600.0
    TOKEN_EXPIRY_BUFFER = 60  # Refrescar 60 segundos antes de expirar

    def __init__(
        self,
        location: str,
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Inicializa el cliente de Vertex AI.

        Args:
            location: Región del endpoint (ej: "us-central1", "europe-west4")
            service_account_file: Ruta al archivo JSON del service account
            service_account_info: Dict con la información del service account
            access_token: Token de acceso directo (alternativa a service account)
            timeout: Timeout en segundos para las requests
        """
        self.location = location
        self.timeout = timeout
        self.project_id: Optional[str] = None

        # Autenticación
        self._access_token = access_token
        self._token_expiry: Optional[float] = None
        self._sa_info: Optional[Dict[str, Any]] = None

        # Cargar service account si se proporciona
        if service_account_file or service_account_info:
            self._sa_info = _load_service_account(
                service_account_file=service_account_file,
                service_account_info=service_account_info,
            )
            self.project_id = self._sa_info.get("project_id")
        elif not access_token:
            raise ValueError(
                "Debe proporcionar service_account_file, service_account_info, o access_token"
            )

    def _get_access_token(self) -> str:
        """Obtiene un token de acceso válido, refrescando si es necesario."""
        # Si tenemos token directo y no expira (o no sabemos cuándo), usarlo
        if self._access_token and self._token_expiry is None and self._sa_info is None:
            return self._access_token

        # Verificar si necesitamos refrescar
        now = time.time()
        if self._access_token and self._token_expiry:
            if now < (self._token_expiry - self.TOKEN_EXPIRY_BUFFER):
                return self._access_token

        # Obtener nuevo token con Service Account
        if self._sa_info:
            jwt = _create_jwt(
                client_email=self._sa_info["client_email"],
                private_key=self._sa_info["private_key"],
                token_uri=self._sa_info["token_uri"],
            )
            token_data = _exchange_jwt_for_token(jwt, self._sa_info["token_uri"])
            self._access_token = token_data["access_token"]
            self._token_expiry = now + token_data.get("expires_in", 3600)
            return self._access_token

        raise RuntimeError("No hay método de autenticación configurado")

    def _build_headers(self) -> Dict[str, str]:
        """Construye los headers necesarios para la API."""
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _get_endpoint(self, model: str, stream: bool = False) -> str:
        """Construye la URL del endpoint."""
        action = "streamGenerateContent" if stream else "generateContent"
        if self.location == "global":
            host = "aiplatform.googleapis.com"
        else:
            host = f"{self.location}-aiplatform.googleapis.com"
        return (
            f"https://{host}/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{model}:{action}"
        )

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
        Genera contenido usando Vertex AI Gemini API.

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
                    f"Vertex AI error: {error_info.get('message', 'Unknown error')}",
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

                buffer = ""
                for chunk in response.iter_text():
                    buffer += chunk
                    # Vertex AI puede enviar múltiples JSON por chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            try:
                                yield json.loads(line)
                            except json.JSONDecodeError:
                                continue


# ============================================================================
# FUNCIÓN DE CONVENIENCIA
# ============================================================================

def fetch_vertexai(
    model: str,
    contents: List[Content],
    location: str,
    service_account_file: Optional[str] = None,
    service_account_info: Optional[Dict[str, Any]] = None,
    access_token: Optional[str] = None,
    stream: bool = False,
    generation_config: Optional[GenerationConfig] = None,
    system_instruction: Optional[str] = None,
    tools: Optional[List[FunctionDeclaration]] = None,
    tool_config: Optional[Dict[str, Any]] = None,
    safety_settings: Optional[List[SafetySetting]] = None,
):
    """
    Función de conveniencia para hacer requests a Vertex AI Gemini API.

    Args:
        model: ID del modelo a usar
        contents: Lista de mensajes de la conversación
        location: Región del endpoint
        service_account_file: Ruta al archivo JSON del service account
        service_account_info: Dict con la información del service account
        access_token: Token de acceso directo (alternativa a service account)
        stream: Si usar streaming o no
        generation_config: Configuración de generación
        system_instruction: Instrucciones del sistema
        tools: Lista de funciones disponibles
        tool_config: Configuración de uso de tools
        safety_settings: Configuración de filtros de seguridad

    Returns:
        GeminiResponse si stream=False
        Iterator[Dict] si stream=True

    Example con Service Account:
        >>> from instantneo.fetchers.vertexai import fetch_vertexai, Content, Part
        >>>
        >>> response = fetch_vertexai(
        ...     model="gemini-2.0-flash",
        ...     location="us-central1",
        ...     service_account_file="path/to/key.json",
        ...     contents=[
        ...         Content(role="user", parts=[Part(text="Hello!")])
        ...     ],
        ... )
        >>> print(response.candidates[0].content.parts[0].text)
    """
    client = VertexAIClient(
        location=location,
        service_account_file=service_account_file,
        service_account_info=service_account_info,
        access_token=access_token,
    )

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
