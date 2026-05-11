"""RunLog — Capa 1: primitivos genéricos de debug-log.

Doc rector: ``docs/design/log-design.md`` sección "Arquitectura en capas"
y "Capa 1 — Primitivos genéricos".

Reglas que sostienen el diseño:

- **Genérico**: no sabe de orquestadores (Loop, Pipeline futuro). Solo
  maneja datos de InstantNeo crudos (``RunInfo``, ``agent.config``,
  ``agent.capabilities``).
- **InstantNeo no se modifica**: los helpers leen desde afuera.
- **JSON-safe**: todo lo que serializamos pasa por ``write_json`` con
  ``default=str`` defensivo.
- **Sanitizado**: ``api_key``, ``service_account_file``, ``location``
  y cualquier key que parezca contener secret nunca se persisten.

Este módulo incluye también la Capa 3 para el caso "InstantNeo solo"
(sin orquestador): ``write_agent_call_log`` y ``load_agent_call_logs``.
La Capa 2 específica del Loop (``RunLog`` con ``turns: list[TurnLog]``)
vive en ``instantneo/loop/debug.py`` y se agrega cuando el Loop se
implementa (PR 8).
"""
from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from instantneo.core import InstantNeo
    from instantneo.models.run_info import RunInfo


# ════════════════════════════════════════════════════════════════════
# Helpers — sanitización y escritura
# ════════════════════════════════════════════════════════════════════

# Keys que siempre se filtran al sanear configs.
_EXPLICIT_SECRET_KEYS = frozenset({
    "api_key", "service_account_file", "location",
})

# Patrones (case-insensitive substring match) que sugieren un secret.
_SECRET_PATTERNS = ("key", "token", "secret", "password", "credential")


def _looks_like_secret(key: str) -> bool:
    """True si ``key`` (case-insensitive) contiene un patrón sospechoso."""
    if key in _EXPLICIT_SECRET_KEYS:
        return True
    lower = key.lower()
    return any(pat in lower for pat in _SECRET_PATTERNS)


def sanitize_secrets(config: dict) -> dict:
    """Devuelve una copia de ``config`` sin keys sensibles.

    Filtra explícitamente: ``api_key``, ``service_account_file``,
    ``location``. Además filtra cualquier key cuyo nombre contenga
    (case-insensitive) ``"key"``, ``"token"``, ``"secret"``,
    ``"password"`` o ``"credential"``.

    Recursivo: aplica a sub-dicts. No muta el input.
    """
    if not isinstance(config, dict):
        return config
    return {
        k: sanitize_secrets(v) if isinstance(v, dict) else v
        for k, v in config.items()
        if not _looks_like_secret(k)
    }


def write_json(path: Path, data: dict) -> None:
    """Escribe ``data`` como JSON a ``path``.

    Usa ``default=str`` para tipos no estándar (datetime, etc.) y
    ``ensure_ascii=False`` para preservar utf-8 correctamente.
    Indent=2 para legibilidad humana.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, default=str, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ════════════════════════════════════════════════════════════════════
# Lectura de capabilities del agente
# ════════════════════════════════════════════════════════════════════

def extract_tool_schemas(agent: "InstantNeo") -> list[dict]:
    """Schemas OpenAI-format de las tools registradas en el agente.

    Thin wrapper sobre ``agent.capabilities.get_schemas()`` (expuesto
    en PR 6). Existe por paridad con el resto de funciones de este
    módulo y para que docs/code apunte a un solo lugar al armar el
    config del agente.
    """
    if not hasattr(agent, "capabilities") or agent.capabilities is None:
        return []
    return agent.capabilities.get_schemas()


def build_agent_config(agent: "InstantNeo") -> dict:
    """Construye la sección ``"agent"`` del config del log.

    Incluye los campos del shape canónico (doc líneas 868-880):

    - ``name``: del agente si existe, default ``"agent"``.
    - ``provider``, ``model``: directo de ``agent.config``.
    - ``role_setup``: original del usuario.
    - ``role_setup_resolved``: composición final via
      ``agent.get_resolved_role_setup()`` (PR 6).
    - ``tools``: schemas via ``extract_tool_schemas`` (PR 6).
    - ``defaults``: snapshot **sanitizado** de los kwargs por-defecto
      del agente (``InstantNeoConfig``).

    Garantiza que ningún secret quede en el output.
    """
    cfg = agent.config

    # Defaults a partir del config del agente — filtramos secrets.
    raw_defaults = {
        "model":             getattr(cfg, "model", None),
        "temperature":       getattr(cfg, "temperature", None),
        "max_tokens":        getattr(cfg, "max_tokens", None),
        "presence_penalty":  getattr(cfg, "presence_penalty", None),
        "frequency_penalty": getattr(cfg, "frequency_penalty", None),
        "stop":              getattr(cfg, "stop", None),
        "seed":              getattr(cfg, "seed", None),
        "stream":            getattr(cfg, "stream", None),
        "logit_bias":        getattr(cfg, "logit_bias", None),
        "images":            getattr(cfg, "images", None),
        "image_detail":      getattr(cfg, "image_detail", None),
        # NO incluir: api_key, location, service_account_file (sanitize
        # se encarga, pero ni siquiera los leemos para no exponerlos
        # accidentalmente en error messages).
    }
    defaults = sanitize_secrets(raw_defaults)

    return {
        "name":                getattr(agent, "name", None) or "agent",
        "provider":            getattr(cfg, "provider", None),
        "model":               getattr(cfg, "model", None),
        "role_setup":          getattr(cfg, "role_setup", None),
        "role_setup_resolved": agent.get_resolved_role_setup(),
        "tools":               extract_tool_schemas(agent),
        "defaults":            defaults,
    }


# ════════════════════════════════════════════════════════════════════
# TurnLog — dataclass + (de)serialización + factoría desde RunInfo
# ════════════════════════════════════════════════════════════════════

@dataclass
class TurnLog:
    """Registro completo de una llamada de ``agent.run()`` (un "turn").

    Mismo shape para todos los contextos: step de un Loop, call solo,
    stage de un Pipeline futuro. La diferencia entre contextos vive
    en el aggregator de Capa 2 (ej. ``RunLog`` del Loop), no acá.

    Doc: ``docs/design/log-design.md`` líneas 137-189.
    """
    # Identificación temporal
    step_num: int
    started_at: str
    completed_at: Optional[str]

    # Lo que el caller mandó al agente
    prompt: str
    images: Optional[list[dict]]      # ver doc — None por ahora (no derivable de RunInfo)
    image_detail: Optional[str]

    # Lo que InstantNeo armó para el provider
    messages_sent: list[dict]
    run_params: dict

    # Lo que el LLM produjo (consolidado al cierre del run)
    response_content: Optional[str]
    reasoning: Optional[str]
    finish_reason: Optional[str]
    usage: Optional[dict]

    # Detalle per-LLM-call (sin raw_response — no serializable)
    llm_calls: list[dict]

    # Ejecución de herramientas en este turn
    tool_executions: list[dict]

    # Provider + modelo
    provider: str
    model: str
    response_id: Optional[str]
    response_model: Optional[str]

    # Timing
    duration_ms: Optional[float]
    provider_timing: Optional[dict]
    request_started_at: str

    # Error si lo hubo
    error: Optional[str]

    # ── Serialización ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialización JSON-safe del TurnLog."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TurnLog":
        """Reconstruye desde la salida de ``to_dict``.

        Tolera dicts con campos extra (los ignora) y con campos
        faltantes (los rellena con defaults razonables).
        """
        # Solo tomamos las keys que TurnLog conoce.
        fields_set = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: data[k] for k in fields_set if k in data}
        # Rellenar campos requeridos faltantes con None / valor neutro.
        defaults = {
            "step_num":         data.get("step_num", 0),
            "started_at":       data.get("started_at", ""),
            "completed_at":     data.get("completed_at"),
            "prompt":           data.get("prompt", ""),
            "images":           data.get("images"),
            "image_detail":     data.get("image_detail"),
            "messages_sent":    data.get("messages_sent", []),
            "run_params":       data.get("run_params", {}),
            "response_content": data.get("response_content"),
            "reasoning":        data.get("reasoning"),
            "finish_reason":    data.get("finish_reason"),
            "usage":            data.get("usage"),
            "llm_calls":        data.get("llm_calls", []),
            "tool_executions":  data.get("tool_executions", []),
            "provider":         data.get("provider", ""),
            "model":            data.get("model", ""),
            "response_id":      data.get("response_id"),
            "response_model":   data.get("response_model"),
            "duration_ms":      data.get("duration_ms"),
            "provider_timing":  data.get("provider_timing"),
            "request_started_at": data.get("request_started_at", ""),
            "error":            data.get("error"),
        }
        defaults.update(kwargs)  # `kwargs` override defaults si vinieron en data
        return cls(**{k: defaults[k] for k in fields_set})

    # ── Factoría desde RunInfo ─────────────────────────────────────

    @classmethod
    def from_runinfo(
        cls,
        *,
        step_num: int,
        started_at: str,
        completed_at: Optional[str],
        run_info: "RunInfo",
    ) -> "TurnLog":
        """Construye un TurnLog desde un ``RunInfo`` (de ``agent.last_run``).

        Args:
            step_num: número del step (1 si es call solo).
            started_at: ISO timestamp del momento en que arrancó el step
                (no la call al LLM, eso es ``request_started_at``).
            completed_at: ISO timestamp del cierre, o None si crasheó.
            run_info: el ``RunInfo`` populado.

        Returns:
            TurnLog con todos los campos mapeados.
        """
        # Serializar LLMCall sin raw_response (no JSON-safe).
        llm_calls_serialized = []
        for c in (run_info.llm_calls or []):
            d = {
                "messages_sent":        getattr(c, "messages_sent", []),
                "response_content":     getattr(c, "response_content", None),
                "finish_reason":        getattr(c, "finish_reason", None),
                "tool_calls_requested": getattr(c, "tool_calls_requested", []),
                "usage":                getattr(c, "usage", None),
                "response_id":          getattr(c, "response_id", None),
                "response_model":       getattr(c, "response_model", None),
                "reasoning_content":    getattr(c, "reasoning_content", None),
            }
            llm_calls_serialized.append(d)

        # Serializar ToolExecution (campos planos, sin _raw_response).
        tool_execs_serialized = []
        for te in (run_info.tool_executions or []):
            tool_execs_serialized.append({
                "name":           getattr(te, "name", None),
                "arguments":      getattr(te, "arguments", {}),
                "result":         getattr(te, "result", None),
                "exception":      getattr(te, "exception", None),
                "execution_mode": getattr(te, "execution_mode", None),
            })

        first_call = run_info.llm_calls[0] if run_info.llm_calls else None
        run_params = run_info.run_params or {}

        return cls(
            step_num=step_num,
            started_at=started_at,
            completed_at=completed_at,
            prompt=run_info.prompt,
            images=None,  # follow-up: derivar de messages_sent
            image_detail=run_params.get("image_detail"),
            messages_sent=run_info.messages_sent or [],
            run_params=run_params,
            response_content=run_info.response_content,
            reasoning=run_info.reasoning,
            finish_reason=run_info.finish_reason,
            usage=run_info.usage,
            llm_calls=llm_calls_serialized,
            tool_executions=tool_execs_serialized,
            provider=run_info.provider,
            model=run_info.model,
            response_id=getattr(first_call, "response_id", None),
            response_model=getattr(first_call, "response_model", None),
            duration_ms=run_info.duration_ms,
            provider_timing=run_info.provider_timing,
            request_started_at=run_info.timestamp,
            error=run_info.error,
        )


# ════════════════════════════════════════════════════════════════════
# Capa 3 — Helpers para uso "InstantNeo solo" (sin Loop)
# ════════════════════════════════════════════════════════════════════

def write_agent_call_log(
    agent: "InstantNeo",
    path: Path | str,
    *,
    call_id: Optional[str] = None,
    started_at: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Path:
    """Persiste el último ``agent.run()`` a un folder.

    Para uso de InstantNeo sin orquestador. Equivale a un único
    ``TurnLog`` serializado en su folder, paralelo a la estructura
    que el Loop usa por step.

    Args:
        agent: instancia de ``InstantNeo``. Debe tener ``agent.last_run``
            poblado (se debió llamar ``agent.run()`` antes).
        path: folder donde escribir. Si no existe, se crea. Se escriben
            dos archivos: ``config.json`` (cabecera del agente) y
            ``call.json`` (TurnLog serializado).
        call_id: UUID opcional para este call. Si no se pasa, se autogenera.
        started_at: ISO UTC del momento en que arrancó la call. Si no se
            pasa, se usa ``agent.last_run.timestamp``.
        extra: dict opcional con metadata custom que va en ``config.json``
            bajo la key ``"extra"``.

    Returns:
        El ``Path`` del folder escrito (resuelto).

    Raises:
        RuntimeError: si ``agent.last_run`` es None.
    """
    if getattr(agent, "last_run", None) is None:
        raise RuntimeError(
            "agent.last_run es None. Debés llamar agent.run(...) antes "
            "de write_agent_call_log()."
        )

    folder = Path(path).resolve()
    folder.mkdir(parents=True, exist_ok=True)

    run_info = agent.last_run
    cid = call_id or uuid.uuid4().hex
    started = started_at or run_info.timestamp or _utcnow_iso()
    captured_at = _utcnow_iso()

    # config.json
    config_payload = {
        "agent":       build_agent_config(agent),
        "captured_at": captured_at,
        "call_id":     cid,
    }
    if extra is not None:
        config_payload["extra"] = extra
    write_json(folder / "config.json", config_payload)

    # call.json (un único TurnLog con step_num=1)
    turn = TurnLog.from_runinfo(
        step_num=1,
        started_at=started,
        completed_at=captured_at,
        run_info=run_info,
    )
    write_json(folder / "call.json", turn.to_dict())

    return folder


def load_agent_call_logs(folder: Path | str) -> list[dict]:
    """Carga todos los call folders presentes en ``folder``.

    Args:
        folder: directorio que contiene subfolders ``<ts>_call_<seq>_<id>/``.
            Si no existe o está vacío, devuelve ``[]``.

    Returns:
        Lista ordenada por nombre de subfolder (timestamp prefix lex-sortable).
        Cada elemento:

            {
                "folder": Path,    # path del call folder
                "config": dict,    # contenido de config.json
                "call":   dict,    # contenido de call.json (raw dict, no TurnLog)
            }

        Skippea subfolders que no tengan ambos archivos.
    """
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        return []

    results = []
    for sub in sorted(folder.iterdir()):
        if not sub.is_dir():
            continue
        config_path = sub / "config.json"
        call_path = sub / "call.json"
        if not (config_path.exists() and call_path.exists()):
            continue
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            call = json.loads(call_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        results.append({"folder": sub, "config": config, "call": call})
    return results


# ────────────────────────────────────────────────────────────────────
# Utilidad local
# ────────────────────────────────────────────────────────────────────

def _utcnow_iso() -> str:
    """ISO 8601 UTC timestamp con `Z` final."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


__all__ = [
    "TurnLog",
    "build_agent_config",
    "extract_tool_schemas",
    "sanitize_secrets",
    "write_json",
    "write_agent_call_log",
    "load_agent_call_logs",
]
