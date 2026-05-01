"""
Autenticación y transporte compartido para Vertex AI.

Centraliza:
- Firma de JWT y obtención de access tokens vía Service Account
- Construcción de URLs de endpoint Vertex AI
- Headers Bearer token

Pensado para ser compuesto vía herencia múltiple con un cliente HTTP de un
provider concreto (AnthropicClient, GeminiClient, etc.):

    class VertexAnthropicClient(VertexAuthMixin, AnthropicClient):
        ...

Requiere 'cryptography' para firmar JWTs con Service Account:
    pip install cryptography
"""

from typing import Any, Dict, Optional
import base64
import httpx
import json
import time


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

    header = {"alg": "RS256", "typ": "JWT"}
    header_b64 = _b64_encode(json.dumps(header, separators=(",", ":")).encode())

    payload = {
        "iss": client_email,
        "scope": scope,
        "aud": token_uri,
        "iat": now,
        "exp": now + lifetime_seconds,
    }
    payload_b64 = _b64_encode(json.dumps(payload, separators=(",", ":")).encode())

    message = f"{header_b64}.{payload_b64}".encode()

    private_key_bytes = private_key.encode() if isinstance(private_key, str) else private_key
    key = serialization.load_pem_private_key(
        private_key_bytes,
        password=None,
        backend=default_backend(),
    )

    signature = key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = _b64_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def _exchange_jwt_for_token(
    jwt: str,
    token_uri: str = "https://oauth2.googleapis.com/token",
) -> Dict[str, Any]:
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

    for field in ("client_email", "private_key"):
        if field not in sa_info:
            raise ValueError(f"Campo requerido faltante en service account: {field}")

    return {
        "client_email": sa_info["client_email"],
        "private_key": sa_info["private_key"],
        "token_uri": sa_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        "project_id": sa_info.get("project_id"),
    }


# ============================================================================
# MIXIN DE TRANSPORTE VERTEX
# ============================================================================

class VertexAuthMixin:
    """
    Encapsula auth GCP, construcción de endpoint Vertex y headers Bearer.

    Cada cliente Vertex (anthropic, gemini, futuros) compone este mixin con
    su cliente directo correspondiente.
    """

    DEFAULT_TIMEOUT = 600.0
    TOKEN_EXPIRY_BUFFER = 60  # Refrescar 60s antes de expirar

    def __init__(
        self,
        location: str,
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.location = location
        self.timeout = timeout
        self.project_id: Optional[str] = None

        self._access_token = access_token
        self._token_expiry: Optional[float] = None
        self._sa_info: Optional[Dict[str, Any]] = None

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
        """Obtiene un access token válido, refrescando si es necesario."""
        if self._access_token and self._token_expiry is None and self._sa_info is None:
            return self._access_token

        now = time.time()
        if self._access_token and self._token_expiry:
            if now < (self._token_expiry - self.TOKEN_EXPIRY_BUFFER):
                return self._access_token

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

    def _vertex_endpoint(self, publisher: str, model: str, action: str) -> str:
        """
        Construye la URL del endpoint Vertex AI.

        Formato:
            https://{host}/v1/projects/{project}/locations/{location}/publishers/{publisher}/models/{model}:{action}

        Soporta location == "global" (sin prefijo de región en el host).
        """
        if self.location == "global":
            host = "aiplatform.googleapis.com"
        else:
            host = f"{self.location}-aiplatform.googleapis.com"
        return (
            f"https://{host}/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/{publisher}/models/{model}:{action}"
        )

    def _build_vertex_headers(self) -> Dict[str, str]:
        """Headers HTTP para Vertex AI con OAuth Bearer token."""
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
