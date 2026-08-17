"""``RunLog`` Capa 2 del sistema de debug — específico del Loop.

Doc rector: ``docs/design/log-design.md`` líneas 192-294
(``RunLog`` dataclass + ``config`` shape + ciclo de vida).

Compone los primitivos de Capa 1 (``TurnLog``, ``build_agent_config``,
``write_json``, ``sanitize_secrets``) de ``instantneo.debug`` en un
aggregator que agrupa N turns más metadata del Loop. Se persiste a un
folder cuando ``debug=True`` en ``InstantLoop``.

Estructura del folder (doc líneas 298-356):

    debug_output/<loop_name>/<YYYYMMDD_HHMMSS>_run_<seq>_<run_id_short>/
        ├── config.json
        ├── turn_001.json
        ├── turn_002.json
        ├── ...
        └── run_end.json
"""
from __future__ import annotations

import datetime
import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from instantneo.debug import TurnLog, write_json, build_agent_config, secure_mkdir

if TYPE_CHECKING:
    from instantneo.history import History


# ════════════════════════════════════════════════════════════════════
# RunLog dataclass
# ════════════════════════════════════════════════════════════════════

@dataclass
class RunLog:
    """Log completo de UN ``loop.run()``.

    Vive en memoria mientras el run corre. Si ``output_path`` está set
    (cuando el Loop construyó este RunLog con ``debug=True``), también
    escribe a disco en cada momento clave:

    - ``write_config()`` al inicio.
    - ``append_turn(turn)`` apenas termina cada step.
    - ``write_run_end()`` al cierre.

    Compatible con ``write_full(path)`` para escribir todo de una.
    """
    # Identificación
    log_id: str
    run_id: str
    loop_name: str
    sequence_num: int

    # Cronología
    started_at: str
    completed_at: Optional[str] = None
    terminated_reason: Optional[str] = None
    stop_reason: Optional[str] = None

    # Cabecera fija (config completo del agente + loop + input)
    config: dict = field(default_factory=dict)

    # Cronología detallada
    turns: list = field(default_factory=list)

    # Folder donde escribir (opcional; si None, no se persiste en cada step)
    output_path: Optional[Path] = None

    # ── (de)serialización ──────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialización JSON-safe del RunLog completo.

        ``turns`` se serializa con ``TurnLog.to_dict()`` por cada uno.
        ``output_path`` se serializa como string (si está set).
        """
        d = asdict(self)
        d["turns"] = [
            (t.to_dict() if hasattr(t, "to_dict") else dict(t))
            for t in self.turns
        ]
        if self.output_path is not None:
            d["output_path"] = str(self.output_path)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RunLog":
        """Reconstruye desde un dict producido por ``to_dict``."""
        turns_data = data.get("turns", [])
        turns = [
            (t if isinstance(t, TurnLog) else TurnLog.from_dict(t))
            for t in turns_data
        ]
        op = data.get("output_path")
        return cls(
            log_id=data.get("log_id", uuid.uuid4().hex),
            run_id=data.get("run_id", ""),
            loop_name=data.get("loop_name", ""),
            sequence_num=data.get("sequence_num", 0),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at"),
            terminated_reason=data.get("terminated_reason"),
            stop_reason=data.get("stop_reason"),
            config=data.get("config", {}),
            turns=turns,
            output_path=Path(op) if op else None,
        )

    # ── Mutadores con escritura incremental ────────────────────────

    def append_turn(self, turn: TurnLog) -> None:
        """Agrega un turn al RunLog y, si hay output_path, lo persiste."""
        self.turns.append(turn)
        if self.output_path is not None:
            # Nombre del archivo: turn_NNN.json (zero-padded a 3 dígitos)
            idx = len(self.turns)
            fname = f"turn_{idx:03d}.json"
            write_json(self.output_path / fname, turn.to_dict())

    def write_config(self) -> None:
        """Escribe ``config.json`` al output_path. No-op si output_path es None."""
        if self.output_path is None:
            return
        payload = {
            "log_id":       self.log_id,
            "run_id":       self.run_id,
            "loop_name":    self.loop_name,
            "sequence_num": self.sequence_num,
            "started_at":   self.started_at,
            **self.config,
        }
        write_json(self.output_path / "config.json", payload)

    def write_run_end(self) -> None:
        """Escribe ``run_end.json`` al output_path. No-op si output_path es None."""
        if self.output_path is None:
            return
        payload = {
            "completed_at":      self.completed_at,
            "terminated_reason": self.terminated_reason,
            "stop_reason":       self.stop_reason,
            "total_steps":       len(self.turns),
            "duration_s":        _duration_seconds(self.started_at, self.completed_at),
        }
        write_json(self.output_path / "run_end.json", payload)

    def write_full(self, path: Optional[Path] = None) -> None:
        """Escribe TODO el log a disco (config + turns + run_end) en una pasada.

        Usa ``path`` si se pasa, sino ``self.output_path``. Si ninguno
        está set, levanta ValueError.
        """
        target = Path(path) if path else self.output_path
        if target is None:
            raise ValueError("RunLog.write_full: ni path ni self.output_path están seteados.")
        # Setear temporalmente para reusar write_config/run_end/append.
        original = self.output_path
        try:
            self.output_path = target
            secure_mkdir(target)
            self.write_config()
            for i, t in enumerate(self.turns, start=1):
                write_json(target / f"turn_{i:03d}.json", t.to_dict())
            self.write_run_end()
        finally:
            self.output_path = original

    # ── Lectura ────────────────────────────────────────────────────

    @classmethod
    def load_folder(cls, path: Path | str) -> "RunLog":
        """Carga un RunLog desde un folder previamente escrito.

        Lee config.json + todos los turn_NNN.json en orden + run_end.json
        (si existe).
        """
        folder = Path(path)
        cfg_path = folder / "config.json"
        if not cfg_path.exists():
            raise FileNotFoundError(f"No existe {cfg_path}")
        config_data = json.loads(cfg_path.read_text(encoding="utf-8"))

        # Separar metadata top-level vs config "anidado"
        top_level_keys = {"log_id", "run_id", "loop_name", "sequence_num", "started_at"}
        meta = {k: config_data[k] for k in top_level_keys if k in config_data}
        nested_config = {k: v for k, v in config_data.items() if k not in top_level_keys}

        # Cargar turns en orden
        turn_files = sorted(folder.glob("turn_*.json"))
        turns: list = []
        for tf in turn_files:
            data = json.loads(tf.read_text(encoding="utf-8"))
            turns.append(TurnLog.from_dict(data))

        # run_end (opcional)
        run_end_path = folder / "run_end.json"
        completed_at = None
        terminated_reason = None
        stop_reason = None
        if run_end_path.exists():
            re_data = json.loads(run_end_path.read_text(encoding="utf-8"))
            completed_at = re_data.get("completed_at")
            terminated_reason = re_data.get("terminated_reason")
            stop_reason = re_data.get("stop_reason")

        return cls(
            log_id=meta.get("log_id", uuid.uuid4().hex),
            run_id=meta.get("run_id", ""),
            loop_name=meta.get("loop_name", ""),
            sequence_num=meta.get("sequence_num", 0),
            started_at=meta.get("started_at", ""),
            completed_at=completed_at,
            terminated_reason=terminated_reason,
            stop_reason=stop_reason,
            config=nested_config,
            turns=turns,
            output_path=folder,
        )


# ════════════════════════════════════════════════════════════════════
# Helpers de creación / lectura masiva
# ════════════════════════════════════════════════════════════════════

def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _duration_seconds(started_at: str, completed_at: Optional[str]) -> Optional[float]:
    if not completed_at or not started_at:
        return None
    try:
        s = datetime.datetime.fromisoformat(started_at)
        c = datetime.datetime.fromisoformat(completed_at)
        return (c - s).total_seconds()
    except Exception:
        return None


def _safe_loop_name(name: str) -> str:
    """Sanea el name para usar como segmento de path.

    Convierte cualquier char no-alfanumérico a underscore. Si queda
    vacío, devuelve 'loop'.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "_", name).strip("_")
    return cleaned or "loop"


def _compute_run_folder(
    base: Path,
    loop_name: str,
    started_at_iso: str,
    sequence_num: int,
    run_id: str,
) -> Path:
    """Compone el path del folder del run según el shape del doc.

    ``<base>/<loop_name>/<YYYYMMDD_HHMMSS>_run_<seq:03d>_<run_id[:6]>/``
    """
    try:
        ts = datetime.datetime.fromisoformat(started_at_iso).strftime("%Y%m%d_%H%M%S")
    except Exception:
        # Fallback: usar momento actual si parsing falla
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id_short = run_id[:6] if run_id else "000000"
    folder_name = f"{ts}_run_{sequence_num:03d}_{run_id_short}"
    return Path(base) / _safe_loop_name(loop_name) / folder_name


def _new_run_log_for_loop(
    *,
    loop_name: str,
    sequence_num: int,
    run_id: str,
    started_at_iso: str,
    config: dict,
    base_path: Optional[Path] = None,
) -> RunLog:
    """Construye un RunLog vacío + setea su output_path si se da base_path.

    Llamado por el Loop al inicio de cada ``.run()`` cuando ``debug=True``.

    Args:
        loop_name, sequence_num, run_id, started_at_iso: identificación.
        config: dict completo (sección agent + loop + input).
        base_path: si se pasa, output_path = ``base_path/<loop_name>/<folder>``.
            Si es None, el RunLog vive solo en memoria (no se persiste).
    """
    log = RunLog(
        log_id=uuid.uuid4().hex,
        run_id=run_id,
        loop_name=loop_name,
        sequence_num=sequence_num,
        started_at=started_at_iso,
        config=config,
    )
    if base_path is not None:
        log.output_path = _compute_run_folder(
            base_path, loop_name, started_at_iso, sequence_num, run_id,
        )
        secure_mkdir(log.output_path)
    return log


def load_run_logs(loop_folder: Path | str) -> list[RunLog]:
    """Carga todos los RunLogs presentes en el folder de un loop.

    Args:
        loop_folder: directorio que contiene subfolders ``<ts>_run_<seq>_<id>/``.

    Returns:
        Lista de ``RunLog`` ordenada por nombre de subfolder
        (timestamp prefix lex-sortable). Skippea folders incompletos
        (sin config.json).
    """
    folder = Path(loop_folder)
    if not folder.exists() or not folder.is_dir():
        return []
    out: list[RunLog] = []
    for sub in sorted(folder.iterdir()):
        if not sub.is_dir():
            continue
        try:
            out.append(RunLog.load_folder(sub))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
    return out


__all__ = [
    "RunLog",
    "load_run_logs",
    "_new_run_log_for_loop",
    "_compute_run_folder",
]
