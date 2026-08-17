"""
Tests de validación de ``location`` y escapado de path en Vertex AI.

Regresión de S5 (revisión de seguridad, docs/security-architecture-review.md):
``location`` se interpolaba sin validar en posición de HOSTNAME
(``f"{location}-aiplatform.googleapis.com"``), así que un valor con ``/``
redirigía la request —y con ella el header ``Authorization: Bearer`` de la
service account— a un host arbitrario. ``project_id`` y ``model`` iban al
path sin escapar.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.fetchers.vertex._auth import VertexAuthMixin, _validate_location


LOCATIONS_INVALIDAS = [
    "x.evil.com/",          # exfiltración del Bearer token a otro host
    "us-central1/../..",    # traversal
    "us-central1:443",
    "us-central1@evil.com",
    "a b",
    "US-CENTRAL1",          # Vertex usa minúsculas
    "-us-central1",
    "us-central1-",
    "",
]

LOCATIONS_VALIDAS = ["us-central1", "europe-west4", "asia-northeast3", "global"]


def test_rechaza_locations_invalidas() -> None:
    for loc in LOCATIONS_INVALIDAS:
        try:
            _validate_location(loc)
        except ValueError:
            continue
        raise AssertionError(f"aceptó location inválida: {loc!r}")


def test_acepta_locations_validas() -> None:
    for loc in LOCATIONS_VALIDAS:
        assert _validate_location(loc) == loc


def test_constructor_valida_location() -> None:
    try:
        VertexAuthMixin(location="x.evil.com/", access_token="t")
    except ValueError:
        return
    raise AssertionError("el constructor aceptó una location maliciosa")


def test_host_no_puede_apuntar_a_otro_dominio() -> None:
    mixin = VertexAuthMixin(location="us-central1", access_token="t")
    assert mixin._vertex_host() == "us-central1-aiplatform.googleapis.com"

    mixin_global = VertexAuthMixin(location="global", access_token="t")
    assert mixin_global._vertex_host() == "aiplatform.googleapis.com"


def test_endpoint_escapa_model_y_project() -> None:
    mixin = VertexAuthMixin(location="us-central1", access_token="t")
    mixin.project_id = "mi-proyecto"

    url = mixin._vertex_endpoint("google", "../../../evil", "generateContent")

    assert "../" not in url
    assert url.startswith("https://us-central1-aiplatform.googleapis.com/v1/")


def test_endpoint_normal_no_se_rompe() -> None:
    """El escapado no puede alterar los nombres legítimos de modelo."""
    mixin = VertexAuthMixin(location="us-central1", access_token="t")
    mixin.project_id = "mi-proyecto"

    url = mixin._vertex_endpoint("google", "gemini-2.5-flash", "generateContent")

    assert url == (
        "https://us-central1-aiplatform.googleapis.com/v1/"
        "projects/mi-proyecto/locations/us-central1/"
        "publishers/google/models/gemini-2.5-flash:generateContent"
    )


def test_openai_compat_endpoint_escapa_project() -> None:
    mixin = VertexAuthMixin(location="us-central1", access_token="t")
    mixin.project_id = "mi-proyecto"

    url = mixin._vertex_openai_compat_endpoint()

    assert url == (
        "https://us-central1-aiplatform.googleapis.com/v1/"
        "projects/mi-proyecto/locations/us-central1/"
        "endpoints/openapi/chat/completions"
    )


TESTS = [
    ("rechaza_locations_invalidas", test_rechaza_locations_invalidas),
    ("acepta_locations_validas", test_acepta_locations_validas),
    ("constructor_valida_location", test_constructor_valida_location),
    ("host_no_apunta_a_otro_dominio", test_host_no_puede_apuntar_a_otro_dominio),
    ("endpoint_escapa_model_y_project", test_endpoint_escapa_model_y_project),
    ("endpoint_normal_no_se_rompe", test_endpoint_normal_no_se_rompe),
    ("openai_compat_escapa_project", test_openai_compat_endpoint_escapa_project),
]


if __name__ == "__main__":
    for name, fn in TESTS:
        fn()
        print(f"  OK  {name}")
    print(f"\n{len(TESTS)} tests pasaron.")
