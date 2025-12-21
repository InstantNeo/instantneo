import base64
import httpx
from typing import List, Dict, Any, Union
from urllib.parse import urlparse

def is_url(path: str) -> bool:
    try:
        result = urlparse(path)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def download_image_to_base64(url: str, timeout: float = 30.0) -> tuple[str, str]:
    """
    Descarga una imagen desde una URL y la convierte a base64.

    Args:
        url: URL de la imagen
        timeout: Timeout en segundos para la descarga

    Returns:
        Tuple de (base64_data, media_type)

    Raises:
        httpx.HTTPError: Si falla la descarga
        ValueError: Si el content-type no es una imagen
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()

        # Obtener media type del header o inferir de la URL
        content_type = response.headers.get("content-type", "").split(";")[0].strip()

        if not content_type.startswith("image/"):
            # Intentar inferir del URL
            content_type = get_media_type_from_extension(url)

        base64_data = base64.b64encode(response.content).decode('utf-8')
        return base64_data, content_type

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

def process_images(images: Union[str, List[str]], image_detail: str) -> List[Dict[str, Any]]:
    """
    Procesa imágenes (URLs o archivos locales) y las convierte a base64.

    Todas las imágenes se convierten a base64 para máxima compatibilidad
    con todos los proveedores de LLM.

    Args:
        images: URL, path local, o lista de URLs/paths
        image_detail: Nivel de detalle (low, high, auto)

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
                img_data, media_type = download_image_to_base64(img_path)
                processed_images.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{img_data}"
                    }
                })
            except Exception as e:
                raise ValueError(f"Error descargando imagen desde {img_path}: {str(e)}")
        else:
            # Archivo local
            media_type = get_media_type_from_extension(img_path)
            img_data = encode_image_to_base64(img_path)
            processed_images.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{img_data}"
                }
            })

    return processed_images