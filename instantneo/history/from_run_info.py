"""Bridge: descompone un ``RunInfo`` en entries del History.

Pieza central que cualquier orquestador (Loop, Pipeline futuro, script
manual) llama una vez por turno después de ``agent.run(prompt)``.

Doc rector: ``docs/design/runinfo-to-entries.md``.

Reglas:

- **Pura**: no muta el ``RunInfo`` recibido.
- **Sin estado**: no recuerda invocaciones previas.
- **No conoce al orquestador**: NO emite ``run_start``, ``step_start``,
  ``step_end``, ``run_end``, ``stop_signal`` — esos los emite el
  orquestador directamente cuando corresponde. El bridge solo emite
  ``response``, ``tool_call``, ``error``.
- **No persiste data pesada**: ``messages_sent`` literal y
  ``raw_response`` quedan fuera del History. Si un orquestador necesita
  esa data, la captura aparte vía el RunLog (``log-design.md``, PR 7).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from instantneo.history.history import History, Entry
    from instantneo.models.run_info import RunInfo


def append_entry_from_run(
    history: "History",
    run_info: "RunInfo",
    *,
    turn_num: int,
    author: str,
    origin: str,
    run_id: str,
) -> "list[Entry]":
    """Descompone un RunInfo en entries y las appendea al History.

    Genera, en orden:

    1. Si ``run_info.error`` está populado: **una sola** entry
       ``type='error'`` y retorna (no emite response ni tool_calls).
    2. Si hay ``response_content`` O si hubo llamada al LLM con
       ``usage``: una entry ``type='response'`` con el shape canónico.
       El campo ``text`` puede ser None cuando el step fue puro
       tool_calls sin texto; la usage queda preservada igual.
    3. Por cada ``ToolExecution`` en ``run_info.tool_executions``: una
       entry ``type='tool_call'``.

    Cada entry generada lleva ``origin``, ``run_id`` y ``turn_num`` en
    su ``content`` para que el log sea filtrable por orquestador, por
    invocación y por turno.

    Args:
        history: instancia de History destino.
        run_info: el ``RunInfo`` de ``agent.last_run`` post-call.
        turn_num: número de turno (responsabilidad del orquestador).
        author: identificador del agente que produjo el run (típicamente
            el ``agent.name`` o un alias). Se usa como ``Entry.author``
            de todas las entries generadas.
        origin: nombre del orquestador que invoca este bridge (p.ej.
            ``loop.name`` si viene de un Loop; ``"manual"`` o lo que el
            autor decida si viene de un script).
        run_id: identificador único de la invocación del orquestador
            (típicamente uuid de ``loop.run()``).

    Returns:
        Lista de las entries appendeadas, en orden.
    """
    appended: list = []

    # Caso 1: run-level error. Una sola entry, cancela el resto.
    if run_info.error:
        appended.append(history.append(
            author=author,
            type="error",
            content={
                "exception":   run_info.error,
                "duration_ms": run_info.duration_ms,
                "provider":    run_info.provider,
                "model":       run_info.model,
                "origin":      origin,
                "run_id":      run_id,
                "turn_num":    turn_num,
            },
        ))
        return appended

    # Caso 2: response.
    # Se emite si hay `response_content` (texto del LLM) O si hubo una
    # llamada al LLM con `usage` aunque ese step fuera puro tool_calls
    # sin texto. Esto garantiza que la usage de TODO step quede en el
    # History — útil para calcular costo total del run sin tener que
    # activar `debug=True`.
    has_text = run_info.response_content is not None
    has_llm_usage = bool(run_info.usage) and bool(run_info.llm_calls)
    if has_text or has_llm_usage:
        first_call = run_info.llm_calls[0] if run_info.llm_calls else None
        appended.append(history.append(
            author=author,
            type="response",
            content={
                "text":               run_info.response_content,
                "reasoning":          run_info.reasoning,
                "finish_reason":      run_info.finish_reason,
                "usage":              run_info.usage,
                "duration_ms":        run_info.duration_ms,
                "provider":           run_info.provider,
                "model":              run_info.model,
                "response_id":        getattr(first_call, "response_id", None),
                "response_model":     getattr(first_call, "response_model", None),
                "provider_timing":    run_info.provider_timing,
                "request_started_at": run_info.timestamp,
                "run_params":         run_info.run_params or {},
                "origin":             origin,
                "run_id":             run_id,
                "turn_num":           turn_num,
            },
        ))

    # Caso 3: tool calls (uno por ToolExecution).
    # `arguments` queda como dict (ya viene parseado de core.py:820 via json.loads).
    # `result` queda nativo (tipo de retorno del tool, sin str()).
    for te in run_info.tool_executions or []:
        appended.append(history.append(
            author=author,
            type="tool_call",
            content={
                "name":           te.name,
                "arguments":      te.arguments,
                "result":         te.result,
                "exception":      te.exception,
                "execution_mode": te.execution_mode,
                "origin":         origin,
                "run_id":         run_id,
                "turn_num":       turn_num,
            },
        ))

    return appended
