"""
Tests de permisos de los archivos persistidos por el RunLog.

Regresión de S6 (revisión de seguridad, docs/security-architecture-review.md):
``write_json`` escribía con el umask del proceso — 0644 con el umask
habitual (022) — y ``mkdir`` dejaba los folders 0755. El contenido incluye
prompts, argumentos y resultados de tools sin redactar (``sanitize_secrets``
solo cubre las keys del config), así que en un host compartido cualquier
usuario local podía leer el historial completo de conversaciones.

Los tests se saltan en plataformas sin permisos POSIX.
"""
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from instantneo.debug import write_json, secure_mkdir

_POSIX = os.name == "posix"


def _mode(p: Path) -> int:
    return os.stat(p).st_mode & 0o777


def test_write_json_crea_archivo_0600() -> None:
    if not _POSIX:
        return
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "run" / "config.json"
        write_json(target, {"prompt": "dato sensible"})
        assert _mode(target) == 0o600, f"archivo en {oct(_mode(target))}"


def test_write_json_crea_directorio_0700() -> None:
    if not _POSIX:
        return
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "run" / "config.json"
        write_json(target, {"prompt": "dato sensible"})
        assert _mode(target.parent) == 0o700, f"directorio en {oct(_mode(target.parent))}"


def test_secure_mkdir_corrige_directorio_existente() -> None:
    """``mkdir(mode=)`` no hace nada si el directorio ya existe.

    Por eso el chmod explícito: si no, un folder de RunLog creado por una
    versión anterior se quedaba permisivo para siempre.
    """
    if not _POSIX:
        return
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "preexistente"
        target.mkdir(mode=0o755)
        os.chmod(target, 0o755)

        secure_mkdir(target)

        assert _mode(target) == 0o700


def test_write_json_sobreescribe_manteniendo_permisos() -> None:
    if not _POSIX:
        return
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "config.json"
        write_json(target, {"v": 1})
        os.chmod(target, 0o644)

        write_json(target, {"v": 2})

        assert _mode(target) == 0o600


def test_contenido_sigue_siendo_legible_para_el_owner() -> None:
    """El endurecimiento no puede romper la lectura del propio proceso."""
    import json
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "run" / "config.json"
        write_json(target, {"agent": {"model": "gpt-5-mini"}, "turns": 3})
        assert json.loads(target.read_text())["turns"] == 3


TESTS = [
    ("write_json_archivo_0600", test_write_json_crea_archivo_0600),
    ("write_json_directorio_0700", test_write_json_crea_directorio_0700),
    ("secure_mkdir_corrige_existente", test_secure_mkdir_corrige_directorio_existente),
    ("sobreescritura_mantiene_permisos", test_write_json_sobreescribe_manteniendo_permisos),
    ("contenido_legible_para_owner", test_contenido_sigue_siendo_legible_para_el_owner),
]


if __name__ == "__main__":
    for name, fn in TESTS:
        fn()
        print(f"  OK  {name}")
    print(f"\n{len(TESTS)} tests pasaron.")
