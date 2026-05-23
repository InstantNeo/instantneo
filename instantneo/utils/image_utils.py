import base64
import ipaddress
import socket
import httpx
from typing import Iterable, List, Dict, Any, Optional, Union
from urllib.parse import urljoin, urlparse

# Máximo de saltos al seguir redirects manualmente (cada salto se revalida).
_MAX_REDIRECTS = 5


def is_url(path: str) -> bool:
    try:
        result = urlparse(path)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def _assert_fetchable_url(url: str, allowed_hosts: Optional[Iterable[str]] = None) -> None:
    """Valida que ``url`` sea segura de descargar server-side (anti-SSRF).

    Rechaza esquemas que no sean http/https y cualquier host que resuelva a
    una dirección privada, loopback, link-local, reservada, multicast o no
    especificada (p.ej. ``169.254.169.254`` de metadata de cloud, ``127.0.0.1``,
    rangos ``10/8`` ``192.168/16``). Un host presente en ``allowed_hosts`` se
    permite explícitamente, saltando el chequeo de IP.

    Raises:
        ValueError: si la URL no es segura de descargar.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Esquema de URL no permitido: {parsed.scheme!r} (solo http/https)")

    host = parsed.hostname
    if not host:
        raise ValueError("URL sin host válido")

    if allowed_hosts and host in set(allowed_hosts):
        return  # opt-in explícito del consumidor

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addrinfo = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"No se pudo resolver el host {host!r}: {e}") from e

    for *_, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(
                f"La URL resuelve a una dirección interna/no enrutable ({ip}); "
                "bloqueada para prevenir SSRF. Usá allowed_hosts si es intencional."
            )

def download_image_to_base64(
    url: str,
    timeout: float = 30.0,
    allowed_hosts: Optional[Iterable[str]] = None,
) -> tuple[str, str]:
    """
    Descarga una imagen desde una URL y la convierte a base64.

    La descarga es server-side, por lo que se valida la URL contra SSRF: se
    rechazan esquemas distintos de http/https y hosts que resuelvan a
    direcciones internas/no enrutables. Los redirects se siguen manualmente
    revalidando cada salto (``follow_redirects`` desactivado para que un 3xx
    no pueda saltar a un destino interno).

    Args:
        url: URL de la imagen
        timeout: Timeout en segundos para la descarga
        allowed_hosts: hosts permitidos explícitamente (omiten el chequeo de IP)

    Returns:
        Tuple de (base64_data, media_type)

    Raises:
        httpx.HTTPError: Si falla la descarga
        ValueError: Si la URL no es segura, hay demasiados redirects, o el
            content-type no es una imagen
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    current_url = url
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            _assert_fetchable_url(current_url, allowed_hosts)
            response = client.get(current_url)

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    break
                current_url = urljoin(current_url, location)
                continue

            response.raise_for_status()

            # Obtener media type del header o inferir de la URL
            content_type = response.headers.get("content-type", "").split(";")[0].strip()
            if not content_type.startswith("image/"):
                content_type = get_media_type_from_extension(current_url)

            base64_data = base64.b64encode(response.content).decode('utf-8')
            return base64_data, content_type

    raise ValueError(f"Demasiados redirects al descargar la imagen desde {url}")

def get_media_type_from_extension(img_path: str) -> str:
    extension = img_path.split('.')[-1].lower()
    if extension in ["jpg", "jpeg"]:
        return "image/jpeg"
    elif extension == "png":
        return "image/png"
    elif extension == "gif":
        return "image/gif"
    elif extension == "webp":
        return "image/webp"
    else:
        raise ValueError("Unsupported image format.")

def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def process_images(
    images: Union[str, List[str]],
    image_detail: str,
    allowed_hosts: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Procesa imágenes (URLs o archivos locales) y las convierte a base64.

    Todas las imágenes se convierten a base64 para máxima compatibilidad
    con todos los proveedores de LLM.

    Las URLs remotas se descargan server-side con validación anti-SSRF (ver
    ``download_image_to_base64``). Si tu caso de uso requiere descargar de un
    host interno, pasalo en ``allowed_hosts``.

    Args:
        images: URL, path local, o lista de URLs/paths
        image_detail: Nivel de detalle (low, high, auto)
        allowed_hosts: hosts internos permitidos explícitamente (opt-in)

    Returns:
        Lista de dicts con las imágenes procesadas en formato base64
    """
    if isinstance(images, str):
        images = [images]

    processed_images = []
    for img_path in images:
        if is_url(img_path):
            # Descargar URL y convertir a base64 para compatibilidad universal
            try:
                img_data, media_type = download_image_to_base64(img_path, allowed_hosts=allowed_hosts)
                processed_images.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{img_data}",
                        "detail": image_detail,
                    }
                })
            except Exception as e:
                raise ValueError(f"Error descargando imagen desde {img_path}: {e}") from e
        else:
            # Archivo local
            media_type = get_media_type_from_extension(img_path)
            img_data = encode_image_to_base64(img_path)
            processed_images.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{img_data}",
                    "detail": image_detail,
                }
            })

    return processed_images