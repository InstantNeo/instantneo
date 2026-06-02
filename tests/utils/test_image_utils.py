"""
Tests de `instantneo.utils.image_utils.process_images`.

Cubre el fix de `image_detail` (PR 1 de v2): el parámetro `image_detail`
debe llegar como campo `detail` dentro del dict `image_url`, para ambos
branches (URL remota y archivo local).

Dual-mode (igual que tests/test_imports.py):
- Compatible con pytest si está instalado: `pytest tests/utils/`.
- Runnable como script standalone: `python3 tests/utils/test_image_utils.py`.

No requiere red ni keys (el branch URL se ejercita con monkeypatch sobre
httpx).
"""

import base64
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Asegurar que se importa el `instantneo` local (de este worktree) y no
# una versión instalada vía pip en site-packages, que podría estar atrás
# del estado actual de la rama. Esto hace al test corrible con:
#   python3 tests/utils/test_image_utils.py
#   pytest tests/utils/
# sin necesidad de PYTHONPATH externo.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.utils.image_utils import process_images


# ─── Helpers de fixture ────────────────────────────────────────────────

# PNG mínimo 1×1 transparente, hex-encoded. Sirve para los tests
# de archivo local sin tener que generar un PNG con PIL.
_TINY_PNG_BYTES = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
    "890000000D49444154789C636000010000000500010D0A2DB40000000049454E"
    "44AE426082"
)


def _write_tiny_png(suffix: str = ".png") -> str:
    """Escribe un PNG temporal de 1x1 y devuelve la ruta absoluta."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(_TINY_PNG_BYTES)
    return path


# ─── Tests sobre branch "archivo local" ────────────────────────────────

def test_process_images_local_includes_detail_low() -> None:
    """Detail 'low' llega al dict como campo `detail`."""
    path = _write_tiny_png()
    try:
        result = process_images(path, "low")
        assert len(result) == 1
        block = result[0]
        assert block["type"] == "image_url"
        assert block["image_url"]["detail"] == "low"
        assert block["image_url"]["url"].startswith("data:image/png;base64,")
    finally:
        os.unlink(path)


def test_process_images_local_includes_detail_high() -> None:
    """Detail 'high' llega al dict como campo `detail`."""
    path = _write_tiny_png()
    try:
        result = process_images(path, "high")
        assert result[0]["image_url"]["detail"] == "high"
    finally:
        os.unlink(path)


def test_process_images_local_includes_detail_auto() -> None:
    """Detail 'auto' llega al dict como campo `detail`."""
    path = _write_tiny_png()
    try:
        result = process_images(path, "auto")
        assert result[0]["image_url"]["detail"] == "auto"
    finally:
        os.unlink(path)


def test_process_images_string_input_wraps_to_list() -> None:
    """Pasar un string (no lista) devuelve lista de 1 elemento."""
    path = _write_tiny_png()
    try:
        result = process_images(path, "auto")  # str, no list
        assert isinstance(result, list)
        assert len(result) == 1
    finally:
        os.unlink(path)


def test_process_images_multiple_images_all_get_detail() -> None:
    """Lista de N imágenes: las N tienen el campo `detail`."""
    path_a = _write_tiny_png()
    path_b = _write_tiny_png()
    try:
        result = process_images([path_a, path_b], "high")
        assert len(result) == 2
        for block in result:
            assert block["image_url"]["detail"] == "high"
            assert block["image_url"]["url"].startswith("data:image/png;base64,")
    finally:
        os.unlink(path_a)
        os.unlink(path_b)


def test_process_images_preserves_existing_url_shape() -> None:
    """Regresión: la url sigue siendo `data:{mime};base64,{data}` con la
    misma codificación que antes del fix. Detecta cualquier cambio
    accidental en la lógica de codificación."""
    path = _write_tiny_png()
    try:
        result = process_images(path, "low")
        url = result[0]["image_url"]["url"]

        # Forma esperada: data:image/png;base64,<base64>
        prefix = "data:image/png;base64,"
        assert url.startswith(prefix)

        # El payload debe decodificar a los mismos bytes que el archivo.
        encoded = url[len(prefix):]
        decoded = base64.b64decode(encoded)
        assert decoded == _TINY_PNG_BYTES
    finally:
        os.unlink(path)


def test_process_images_jpeg_mime_detection() -> None:
    """Verifica que el mime de la url se infiere de la extensión, no se hardcodea."""
    # Misma data PNG pero con extensión jpg — fuerza la rama de get_media_type
    # a devolver "image/jpeg" según la extensión, no según el contenido.
    fd, path = tempfile.mkstemp(suffix=".jpg")
    with os.fdopen(fd, "wb") as f:
        f.write(_TINY_PNG_BYTES)
    try:
        result = process_images(path, "auto")
        assert result[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert result[0]["image_url"]["detail"] == "auto"
    finally:
        os.unlink(path)


# ─── Tests sobre branch "URL remota" (mockeado) ────────────────────────

def _make_mock_httpx_response(content: bytes, content_type: str) -> MagicMock:
    """Construye un mock de respuesta httpx con bytes y content-type dados."""
    response = MagicMock()
    response.content = content
    response.headers = {"content-type": content_type}
    response.is_redirect = False
    response.raise_for_status = MagicMock(return_value=None)
    return response


def _fake_public_getaddrinfo(*_args, **_kwargs):
    """Resuelve cualquier host a una IP pública fija (evita DNS real)."""
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def test_process_images_url_includes_detail() -> None:
    """URL remota: el dict resultante incluye `detail` y `url`.
    Mockea httpx.Client para no salir a internet."""
    fake_response = _make_mock_httpx_response(_TINY_PNG_BYTES, "image/png")

    mock_client_instance = MagicMock()
    mock_client_instance.get.return_value = fake_response
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)

    with patch("instantneo.utils.image_utils.httpx.Client", return_value=mock_client_instance), \
         patch("instantneo.utils.image_utils.socket.getaddrinfo", _fake_public_getaddrinfo):
        result = process_images("https://example.com/test.png", "high")

    assert len(result) == 1
    block = result[0]
    assert block["type"] == "image_url"
    assert block["image_url"]["detail"] == "high"
    assert block["image_url"]["url"].startswith("data:image/png;base64,")


def test_process_images_url_preserves_base64_payload() -> None:
    """URL remota: la url contiene el base64 de los bytes descargados."""
    fake_response = _make_mock_httpx_response(_TINY_PNG_BYTES, "image/png")

    mock_client_instance = MagicMock()
    mock_client_instance.get.return_value = fake_response
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)

    with patch("instantneo.utils.image_utils.httpx.Client", return_value=mock_client_instance), \
         patch("instantneo.utils.image_utils.socket.getaddrinfo", _fake_public_getaddrinfo):
        result = process_images("https://example.com/test.png", "auto")

    url = result[0]["image_url"]["url"]
    prefix = "data:image/png;base64,"
    assert url.startswith(prefix)
    decoded = base64.b64decode(url[len(prefix):])
    assert decoded == _TINY_PNG_BYTES


# ─── Tests anti-SSRF ───────────────────────────────────────────────────

from instantneo.utils.image_utils import download_image_to_base64


def _expect_value_error(fn) -> None:
    """Asegura que fn() lanza ValueError (sin depender de pytest)."""
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("Se esperaba ValueError pero no se lanzó")


def test_blocks_private_ip() -> None:
    """Una URL que resuelve a un rango privado (10/8) es rechazada."""
    _expect_value_error(lambda: download_image_to_base64("http://10.0.0.1/x.png"))


def test_blocks_loopback() -> None:
    """Loopback (127.0.0.1) es rechazado."""
    _expect_value_error(lambda: download_image_to_base64("http://127.0.0.1/x.png"))


def test_blocks_cloud_metadata_endpoint() -> None:
    """El endpoint link-local de metadata de cloud (169.254.169.254) es rechazado."""
    _expect_value_error(lambda: download_image_to_base64("http://169.254.169.254/latest/meta-data/"))


def test_blocks_non_http_scheme() -> None:
    """Esquemas distintos de http/https (file://, gopher://) son rechazados."""
    _expect_value_error(lambda: download_image_to_base64("file:///etc/passwd"))


def test_allowed_hosts_bypass_permits_internal() -> None:
    """Un host interno listado en allowed_hosts se permite explícitamente."""
    fake_response = _make_mock_httpx_response(_TINY_PNG_BYTES, "image/png")
    mock_client = MagicMock()
    mock_client.get.return_value = fake_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("instantneo.utils.image_utils.httpx.Client", return_value=mock_client):
        data, media_type = download_image_to_base64(
            "http://10.0.0.5/internal.png", allowed_hosts={"10.0.0.5"}
        )

    assert media_type == "image/png"
    assert base64.b64decode(data) == _TINY_PNG_BYTES


def test_redirect_to_internal_is_blocked() -> None:
    """Un 3xx que apunta a una IP interna se revalida y se bloquea
    (los redirects no se siguen automáticamente)."""
    redirect_resp = MagicMock()
    redirect_resp.is_redirect = True
    redirect_resp.headers = {"location": "http://169.254.169.254/"}

    mock_client = MagicMock()
    mock_client.get.return_value = redirect_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    # Empezamos en una IP pública literal (sin DNS); el redirect apunta a
    # link-local, que la segunda validación debe rechazar.
    with patch("instantneo.utils.image_utils.httpx.Client", return_value=mock_client):
        _expect_value_error(lambda: download_image_to_base64("http://93.184.216.34/test.png"))


# ─── Runner standalone (sin pytest) ────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("process_images_local_includes_detail_low",  test_process_images_local_includes_detail_low),
        ("process_images_local_includes_detail_high", test_process_images_local_includes_detail_high),
        ("process_images_local_includes_detail_auto", test_process_images_local_includes_detail_auto),
        ("process_images_string_input_wraps_to_list", test_process_images_string_input_wraps_to_list),
        ("process_images_multiple_images_all_get_detail", test_process_images_multiple_images_all_get_detail),
        ("process_images_preserves_existing_url_shape", test_process_images_preserves_existing_url_shape),
        ("process_images_jpeg_mime_detection",         test_process_images_jpeg_mime_detection),
        ("process_images_url_includes_detail",         test_process_images_url_includes_detail),
        ("process_images_url_preserves_base64_payload", test_process_images_url_preserves_base64_payload),
        ("blocks_private_ip",                          test_blocks_private_ip),
        ("blocks_loopback",                            test_blocks_loopback),
        ("blocks_cloud_metadata_endpoint",             test_blocks_cloud_metadata_endpoint),
        ("blocks_non_http_scheme",                     test_blocks_non_http_scheme),
        ("allowed_hosts_bypass_permits_internal",      test_allowed_hosts_bypass_permits_internal),
        ("redirect_to_internal_is_blocked",            test_redirect_to_internal_is_blocked),
    ]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")

    print()
    total = len(tests)
    passed = total - len(failures)
    print(f"PASS: {passed} / {total}")
    if failures:
        sys.exit(1)
