"""
Tests transversales después del PR 2 (cross PR 1 + PR 2).

Verifican que el fix de ``image_detail`` (PR 1) y el ``History`` (PR 2)
interactúan correctamente en escenarios de uso real:

- El dict producido por ``process_images`` puede guardarse en una entry
  del History (caso típico para el bridge futuro).
- El roundtrip ``to_json`` / ``from_dicts`` preserva el campo ``detail``.
- Múltiples imágenes con detail distinto sobreviven a serialización.

Dual-mode. No requieren red ni LLM.
"""
import sys
import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.history import History
from instantneo.utils.image_utils import process_images


# PNG mínimo 1×1 transparente para tests sin generar imágenes reales.
_TINY_PNG_BYTES = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
    "890000000D49444154789C636000010000000500010D0A2DB40000000049454E"
    "44AE426082"
)


def _write_tiny_png() -> str:
    fd, path = tempfile.mkstemp(suffix=".png")
    with os.fdopen(fd, "wb") as f:
        f.write(_TINY_PNG_BYTES)
    return path


# ════════════════════════════════════════════════════════════════════
# PR 1 + PR 2: image_detail sobrevive el roundtrip via History
# ════════════════════════════════════════════════════════════════════

def test_image_detail_local_payload_stored_roundtrip() -> None:
    """Procesar imagen local con detail='high' → guardar en History →
    roundtrip a JSON y vuelta → detail sobrevive."""
    path = _write_tiny_png()
    try:
        # PR 1: producir el payload con detail
        images = process_images(path, "high")
        assert images[0]["image_url"]["detail"] == "high"

        # PR 2: appendear ese payload como contenido de una entry
        h = History(name="test")
        h.append(
            author="bridge_simulated",
            type="prompt",
            content={"text": "describe la imagen", "images": images},
        )

        # Roundtrip
        js = h.to_json()
        h2 = History.from_dicts(json.loads(js))

        # Verificar que detail sobrevivió
        restored = h2.all()[0]
        assert restored.content["images"][0]["image_url"]["detail"] == "high"
        # Y que el url base64 también sobrevivió (regresión cruzada)
        assert restored.content["images"][0]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
    finally:
        os.unlink(path)


def test_image_detail_url_payload_stored_roundtrip() -> None:
    """Mismo patrón pero con URL (httpx mockeado para no salir a internet)."""
    fake_response = MagicMock()
    fake_response.content = _TINY_PNG_BYTES
    fake_response.headers = {"content-type": "image/png"}
    fake_response.is_redirect = False
    fake_response.raise_for_status = MagicMock(return_value=None)

    client_mock = MagicMock()
    client_mock.get.return_value = fake_response
    client_mock.__enter__ = MagicMock(return_value=client_mock)
    client_mock.__exit__ = MagicMock(return_value=False)

    # getaddrinfo fijo a IP pública: evita DNS real y pasa la validación anti-SSRF.
    def _fake_getaddrinfo(*_a, **_k):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    with patch("instantneo.utils.image_utils.httpx.Client", return_value=client_mock), \
         patch("instantneo.utils.image_utils.socket.getaddrinfo", _fake_getaddrinfo):
        images = process_images("https://example.com/img.png", "low")

    assert images[0]["image_url"]["detail"] == "low"

    h = History()
    h.append(author="bridge", type="prompt",
             content={"text": "x", "images": images})
    h2 = History.from_dicts(json.loads(h.to_json()))

    assert h2.all()[0].content["images"][0]["image_url"]["detail"] == "low"


def test_multiple_image_blocks_with_different_details_in_one_entry() -> None:
    """3 imágenes con detail distinto, una sola entry — todas sobreviven."""
    path_a = _write_tiny_png()
    path_b = _write_tiny_png()
    path_c = _write_tiny_png()
    try:
        a = process_images(path_a, "low")
        b = process_images(path_b, "high")
        c = process_images(path_c, "auto")
        all_images = a + b + c  # 3 dicts

        h = History()
        h.append(author="bridge", type="prompt",
                 content={"text": "compare 3 images", "images": all_images})

        h2 = History.from_dicts(json.loads(h.to_json()))
        restored = h2.all()[0]

        details = [img["image_url"]["detail"] for img in restored.content["images"]]
        assert details == ["low", "high", "auto"]
    finally:
        for p in [path_a, path_b, path_c]:
            os.unlink(p)


def test_image_payload_stored_and_filterable_by_type() -> None:
    """Entries de tipo 'prompt' con imágenes son recuperables vía by_type."""
    path = _write_tiny_png()
    try:
        images = process_images(path, "high")
        h = History()
        h.append(author="agent", type="response",
                 content={"text": "respuesta sin imagen"})
        h.append(author="bridge", type="prompt",
                 content={"text": "pregunta con imagen", "images": images})
        h.append(author="orchestrator", type="step_end", content={})

        prompts = h.by_type("prompt")
        assert len(prompts) == 1
        assert "images" in prompts[0].content
        assert prompts[0].content["images"][0]["image_url"]["detail"] == "high"
    finally:
        os.unlink(path)


# ════════════════════════════════════════════════════════════════════
# Runner standalone
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("image_detail_local_payload_stored_roundtrip",
         test_image_detail_local_payload_stored_roundtrip),
        ("image_detail_url_payload_stored_roundtrip",
         test_image_detail_url_payload_stored_roundtrip),
        ("multiple_image_blocks_with_different_details_in_one_entry",
         test_multiple_image_blocks_with_different_details_in_one_entry),
        ("image_payload_stored_and_filterable_by_type",
         test_image_payload_stored_and_filterable_by_type),
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
    print(f"PASS: {total - len(failures)} / {total}")
    if failures:
        sys.exit(1)
