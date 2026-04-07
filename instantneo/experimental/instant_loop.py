"""InstantLoop — orquestador genérico de agente en loop.

Corre cualquier InstantNeo en un loop multi-turno con historial acumulado.
Agnóstico al dominio — recibe configuración y produce resultado + trace.

Puede usarse con cualquier tipo de agente (investigador, clasificador,
analista, etc.) simplemente cambiando las tools, el prompt template y
la stop_tool.

# TODO — Propuesta de Diego:
# - Desacoplar la herramienta de historial para que pueda ser reutilizada
#   y manejada en sistemas multiagente (donde varios agentes comparten o
#   intercambian historial).
# - Desacoplar el manejo de memoria para que pueda inyectarse externamente,
#   permitiendo estrategias de memoria compartida, persistente o selectiva.
# - Actualmente InstantLoop maneja historial y memoria internamente.
#   Esto funciona para un agente solo, pero no es óptimo para arquitecturas
#   más complejas y eficientes donde múltiples agentes colaboran o donde
#   el historial necesita persistir entre sesiones.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class InstantLoop:
    """Orquestador genérico que corre cualquier InstantNeo en loop con historial.

    Ejecuta un agente InstantNeo en turnos sucesivos, acumulando historial
    entre turnos, hasta que el agente llame a una tool de finalización
    (stop_tool) o se agoten los turnos.

    Args:
        agent: Instancia de InstantNeo configurada con tools y system prompt.
        stop_tool: Nombre de la tool que señala fin del loop.
            Cuando el agente la llama, el loop termina y los argumentos
            de esa tool se devuelven como resultado.
        max_turns: Máximo de turnos antes de forzar parada.
        debug_dir: Directorio base para debug. Por cada run se crea una
            subcarpeta con timestamp y nombre de config.
        debug_run_dir: Carpeta de debug pre-creada. Si se pasa, se usa
            directamente sin crear subcarpeta. Tiene prioridad sobre debug_dir.
        agent_config: Dict de configuración del agente (se incluye en
            los archivos de debug para trazabilidad completa).
        images: Imágenes para incluir en cada turno. Rutas a archivos
            o URLs, igual que en InstantNeo.
        image_detail: Nivel de detalle de las imágenes ("auto", "low", "high").
    """

    def __init__(
        self,
        agent,
        stop_tool: str = "report_classification",
        max_turns: int = 30,
        debug_dir: str | Path | None = None,
        debug_run_dir: str | Path | None = None,
        agent_config: dict | None = None,
        images: str | list[str] | None = None,
        image_detail: str | None = None,
    ):
        self.agent = agent
        self.stop_tool = stop_tool
        self.max_turns = max_turns
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self.debug_run_dir = Path(debug_run_dir) if debug_run_dir else None
        self.agent_config = agent_config or {}
        self.images = images
        self.image_detail = image_detail

    def run(self, prompt: str) -> dict:
        """Ejecuta el loop completo.

        Args:
            prompt: Instrucción inicial para el agente. Se envía en el
                primer turno. En los turnos siguientes el agente recibe
                solo el historial (que ya incluye esta instrucción).

        Returns:
            {"result": dict, "trace": dict} donde trace incluye turns,
            timing, usage, history, tool_usage_counts.
        """
        history = []
        turns = []
        result = None
        total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        started_at = datetime.now(timezone.utc)

        # Crear carpeta de debug y progress inicial
        run_dir = None
        if self.debug_run_dir:
            # Carpeta pre-creada (evals u otro caller que controla la estructura)
            run_dir = self.debug_run_dir
            run_dir.mkdir(parents=True, exist_ok=True)
        elif self.debug_dir:
            # Crear subcarpeta automática con timestamp y nombre de config
            config_name = self.agent_config.get("name", "unknown")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = self.debug_dir / f"{ts}_{config_name}"
            run_dir.mkdir(parents=True, exist_ok=True)

        if run_dir:
            self._write_progress(run_dir, prompt, started_at, "running",
                                 turns, total_usage, None, None)

        for turn_num in range(1, self.max_turns + 1):
            turn_prompt = self._build_prompt(prompt, history, turn_num)

            logger.info("Turn %d/%d (prompt=%d chars)", turn_num, self.max_turns, len(turn_prompt))

            # Marcar turno en progreso
            if run_dir:
                self._write_progress(run_dir, prompt, started_at, "running",
                                     turns, total_usage, None, None,
                                     in_progress_turn=turn_num)

            # Retry con backoff para timeouts de API
            for attempt in range(3):
                try:
                    self.agent.run(
                        turn_prompt,
                        images=self.images,
                        image_detail=self.image_detail,
                    )
                    break
                except Exception as e:
                    if attempt < 2 and "timed out" in str(e).lower():
                        wait = (attempt + 1) * 10
                        logger.warning(
                            "API timeout en turn %d, retry en %ds...", turn_num, wait
                        )
                        time.sleep(wait)
                    else:
                        raise

            # Extraer trace estructurado del turno
            run_info = self.agent.last_run
            turn_trace = self._extract_turn_trace(run_info, turn_num)

            # Siempre capturar prompt enviado (se usa en debug)
            turn_trace["prompt_sent"] = turn_prompt

            turns.append(turn_trace)

            # Acumular usage
            turn_usage = turn_trace.get("usage") or {}
            for key in total_usage:
                total_usage[key] += turn_usage.get(key, 0)

            # Log del turno
            duration_str = f"{turn_trace.get('duration_ms', 0):.0f}ms"
            tools_in_turn = len(turn_trace.get("tool_executions", []))
            tokens_in_turn = turn_usage.get("total_tokens", 0)
            logger.info(
                "Turn %d (%s) tools=%d, tokens=%d, finish=%s",
                turn_num, duration_str, tools_in_turn, tokens_in_turn,
                turn_trace.get("finish_reason"),
            )

            # Actualizar progress después del turno
            if run_dir:
                self._write_progress(run_dir, prompt, started_at, "running",
                                     turns, total_usage, None, None)

            # Acumular historial (solo el delta de este turno)
            history.append({"type": "turn_marker", "turn": turn_num})

            if run_info and run_info.response_content:
                history.append({"type": "response", "text": run_info.response_content})

            for te in (run_info.tool_executions if run_info else []) or []:
                # Args formateados sin razonamiento para display en historial
                display_args = ", ".join(
                    f"{k}='{v}'" for k, v in te.arguments.items()
                    if k != "razonamiento"
                )
                history.append({
                    "type": "tool",
                    "tool": te.name,
                    "args": display_args,
                    "result": str(te.result),
                    "razonamiento": te.arguments.get("razonamiento", ""),
                })

                if te.name == self.stop_tool:
                    result = dict(te.arguments)
                    break

            if result is not None:
                # Capturar justificación del último response_text
                response_text = (turn_trace.get("response_text") or "").strip()
                if response_text:
                    result["justificacion"] = response_text
                logger.info("Loop completado en turn %d", turn_num)
                break

        completed_at = datetime.now(timezone.utc)

        # Conteo de uso por herramienta
        tool_usage_counts: dict[str, int] = {}
        for turn_data in turns:
            for te in turn_data.get("tool_executions", []):
                name = te.get("name", "unknown")
                tool_usage_counts[name] = tool_usage_counts.get(name, 0) + 1

        trace = {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "total_duration_s": round((completed_at - started_at).total_seconds(), 2),
            "total_turns": len(turns),
            "total_tool_executions": sum(
                len(t.get("tool_executions", [])) for t in turns
            ),
            "total_usage": total_usage,
            "tool_usage_counts": tool_usage_counts,
            "history": history,
            "turns": turns,
        }

        # Escribir debug files si está configurado
        if run_dir:
            final_result = result or {"error": f"No llamó {self.stop_tool}"}
            status = "completed" if result else "error"
            error = None if result else f"No llamó {self.stop_tool} en {self.max_turns} turnos"
            self._write_progress(run_dir, prompt, started_at, status,
                                 turns, total_usage, final_result, error)
            self._write_debug_files(run_dir, prompt, final_result, trace)

        return {
            "result": result or {"error": f"No llamó {self.stop_tool}"},
            "trace": trace,
        }

    def _extract_turn_trace(self, run_info, turn_num: int) -> dict:
        """Extrae trace completo de un turno desde RunInfo.

        Captura todos los campos disponibles en RunInfo, LLMCall y
        ToolExecution para trazabilidad completa en debug.
        """
        if not run_info:
            return {"turn": turn_num, "error": "no run_info available"}

        # Tool executions completas
        tool_execs = []
        for te in (run_info.tool_executions or []):
            tool_execs.append({
                "name": te.name,
                "arguments": te.arguments,
                "result": str(te.result) if te.result is not None else None,
                "exception": te.exception,
                "execution_mode": getattr(te, "execution_mode", None),
            })

        # LLM calls completos (puede haber más de uno por turno)
        llm_calls = []
        for lc in (run_info.llm_calls or []):
            llm_call_data = {
                "response_content": lc.response_content,
                "finish_reason": lc.finish_reason,
                "usage": lc.usage,
                "reasoning_content": getattr(lc, "reasoning_content", None),
                "response_id": getattr(lc, "response_id", None),
                "response_model": getattr(lc, "response_model", None),
                "tool_calls_requested": getattr(lc, "tool_calls_requested", None),
                "messages_sent": getattr(lc, "messages_sent", None),
            }
            llm_calls.append(llm_call_data)

        # Texto de respuesta consolidado (para compatibilidad)
        all_response_text = run_info.response_content or ""
        llm_texts = []
        for lc in (run_info.llm_calls or []):
            if lc.response_content:
                llm_texts.append(lc.response_content)
            if getattr(lc, "reasoning_content", None):
                llm_texts.append(f"[reasoning] {lc.reasoning_content}")
        if llm_texts:
            combined = "\n".join(llm_texts)
            if combined and combined != all_response_text:
                all_response_text = combined

        return {
            "turn": turn_num,
            # RunInfo top-level
            "provider": getattr(run_info, "provider", None),
            "model": getattr(run_info, "model", None),
            "execution_mode": getattr(run_info, "execution_mode", None),
            "stream": getattr(run_info, "stream", None),
            "timestamp": getattr(run_info, "timestamp", None),
            "duration_ms": round(run_info.duration_ms, 1) if run_info.duration_ms else None,
            "finish_reason": run_info.finish_reason,
            "usage": run_info.usage,
            "error": getattr(run_info, "error", None),
            "reasoning": getattr(run_info, "reasoning", None),
            "run_params": getattr(run_info, "run_params", None),
            "provider_timing": run_info.provider_timing,
            # Contenido
            "response_text": all_response_text or None,
            "llm_calls": llm_calls,
            "tool_executions": tool_execs,
        }

    def _build_prompt(self, initial_prompt: str, history: list[dict], turn_num: int) -> str:
        """Construye el prompt para el turno actual.

        Turno 1: envía la instrucción inicial tal cual.
        Turno 2+: envía solo el historial (que ya incluye la instrucción
        inicial marcada como user:).
        """
        if turn_num == 1:
            return initial_prompt
        return self._format_history(initial_prompt, history, turn_num)

    def _format_history(self, initial_prompt: str, history: list[dict], turn_num: int) -> str:
        """Formatea el historial acumulado con estructura clara.

        Incluye la instrucción inicial como user: y las respuestas del
        agente como assistant:, con herramientas y resultados.
        """
        if not history:
            return ""

        parts = []
        parts.append(f"Estás en el turno {turn_num} de {self.max_turns} posibles.")
        parts.append("")

        # Instrucción inicial como contexto
        parts.append("## Instrucción inicial")
        parts.append(f"user: {initial_prompt}")
        parts.append("")
        parts.append("<historial>")

        # Agrupar entries por turno
        turns: dict[int, dict] = {}
        current_turn = None
        for entry in history:
            if entry["type"] == "turn_marker":
                current_turn = entry["turn"]
                turns[current_turn] = {"tools": [], "response": None}
            elif current_turn is not None:
                if entry["type"] == "tool":
                    turns[current_turn]["tools"].append(entry)
                elif entry["type"] == "response":
                    turns[current_turn]["response"] = entry["text"]

        tool_num = 0
        for t_num, t_data in sorted(turns.items()):
            parts.append("")
            parts.append(f"## Turno {t_num}")

            # Subsección: herramientas
            if t_data["tools"]:
                parts.append("")
                parts.append("### Herramientas que usaste y sus resultados")
                parts.append("")
                for te in t_data["tools"]:
                    tool_num += 1
                    args_str = te["args"]
                    parts.append(f"**{tool_num}. {te['tool']}**({args_str})")
                    if te.get("razonamiento"):
                        parts.append(f"  razonamiento: {te['razonamiento']}")
                    parts.append(f"  resultado: {te['result']}")
                    parts.append("")

            # Subsección: respuesta del modelo
            if t_data["response"]:
                parts.append("### assistant:")
                parts.append("")
                parts.append(t_data["response"])
                parts.append("")

        parts.append("</historial>")

        # Instrucción según turno
        if turn_num == self.max_turns:
            parts.append("")
            parts.append(
                "⚠️ ESTE ES TU ÚLTIMO TURNO. Debés concluir AHORA. "
                f"Llamá a {self.stop_tool} con tu mejor análisis, sea conclusivo o no."
            )
        elif history:
            parts.append("")
            parts.append(
                "Razoná sobre lo que encontraste hasta ahora: "
                "¿qué descartaste y por qué? ¿qué te falta verificar? "
                "Luego actuá en consecuencia."
            )

        return "\n".join(parts)

    # ── Debug output ────────────────────────────────────────────

    def _write_progress(
        self,
        run_dir: Path,
        input_prompt: str,
        started_at: datetime,
        status: str,
        turns: list[dict],
        total_usage: dict,
        result: dict | None,
        error: str | None,
        in_progress_turn: int | None = None,
    ) -> None:
        """Escribe/actualiza progress.json con el estado actual del run.

        Se llama antes de cada turno (in_progress), después de cada turno
        (completed), y al finalizar el run.
        """
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

        turns_progress = []
        for t in turns:
            turn_usage = t.get("usage") or {}
            turns_progress.append({
                "turn": t["turn"],
                "status": "completed",
                "duration_ms": t.get("duration_ms"),
                "tokens": turn_usage.get("total_tokens", 0),
                "tools_called": [te["name"] for te in t.get("tool_executions", [])],
                "finish_reason": t.get("finish_reason"),
                "response_text": t.get("response_text"),
                "reasoning": t.get("reasoning"),
            })

        # Turno en progreso (aún sin resultado)
        if in_progress_turn is not None:
            turns_progress.append({
                "turn": in_progress_turn,
                "status": "in_progress",
                "duration_ms": None,
                "tokens": None,
                "tools_called": [],
                "finish_reason": None,
                "response_text": None,
                "reasoning": None,
            })

        progress = {
            "status": status,
            "config_name": self.agent_config.get("name"),
            "model": self.agent_config.get("model"),
            "prompt": input_prompt,
            "started_at": started_at.isoformat(),
            "current_turn": in_progress_turn or len(turns),
            "max_turns": self.max_turns,
            "elapsed_s": round(elapsed, 1),
            "tokens": {
                "input": total_usage.get("input_tokens", 0),
                "output": total_usage.get("output_tokens", 0),
                "total": total_usage.get("total_tokens", 0),
            },
            "turns": turns_progress,
            "result": result,
            "error": error,
        }

        progress_path = run_dir / "progress.json"
        progress_path.write_text(
            json.dumps(progress, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def _write_debug_files(self, run_dir: Path, input_prompt: str, result: dict | None, trace: dict) -> None:
        """Genera archivos de debug completos al finalizar el run.

        Archivos:
            trace.json      — dump completo: config + trace + resultado (máquinas)
            report.md       — markdown técnico con config, métricas y turnos detallados
            report.json     — JSON estructurado sin historial redundante (dashboards)
            agent_trace.md  — narrativa limpia del proceso del agente (lectura humana)
        """
        # 1. trace.json — dump completo
        trace_data = {
            "config": self._sanitize_config(),
            "input": {"prompt": input_prompt},
            "result": result,
            "trace": trace,
        }
        (run_dir / "trace.json").write_text(
            json.dumps(trace_data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        # 2. report.md — markdown técnico
        (run_dir / "report.md").write_text(
            self._build_debug_md(input_prompt, result, trace),
            encoding="utf-8",
        )

        # 3. report.json — JSON estructurado
        (run_dir / "report.json").write_text(
            json.dumps(self._build_debug_json(input_prompt, result, trace), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        # 4. agent_trace.md — narrativa limpia del proceso
        (run_dir / "agent_trace.md").write_text(
            self._build_agent_trace(input_prompt, result, trace),
            encoding="utf-8",
        )

        logger.info("Debug files written to: %s", run_dir)

    def _build_agent_trace(self, input_prompt: str, result: dict | None, trace: dict) -> str:
        """Genera narrativa limpia del proceso del agente.

        Sin redundancias: config e input una sola vez al inicio,
        cada turno muestra solo el delta (respuesta + tools nuevas).
        Sin prompts completos — esos están en report.md/trace.json.
        """
        config = self._sanitize_config()
        lines = []

        # Header con contexto (una sola vez)
        lines.append(f"# Traza del Agente: {config.get('name', '?')}")
        lines.append("")
        lines.append(f"**Modelo**: {config.get('model')} | "
                     f"**Provider**: {config.get('provider')} | "
                     f"**Temperature**: {config.get('temperature')}")
        lines.append(f"**Prompt**: {config.get('system_prompt')} | "
                     f"**Referencias**: {config.get('references_version')}")
        lines.append("")
        lines.append(f"**Input**: {input_prompt}")
        lines.append("")

        # Resumen rápido
        total_turns = trace.get("total_turns", 0)
        usage = trace.get("total_usage", {})
        duration = trace.get("total_duration_s", 0)
        lines.append(f"**Resumen**: {total_turns} turnos | "
                     f"{usage.get('total_tokens', 0):,} tokens | "
                     f"{duration:.0f}s")
        lines.append("")
        lines.append("---")

        # Turnos — solo el delta
        tool_num = 0
        for turn_data in trace.get("turns", []):
            turn = turn_data["turn"]
            turn_usage = turn_data.get("usage") or {}
            dur_ms = turn_data.get("duration_ms", 0)
            finish = turn_data.get("finish_reason", "?")
            tool_execs = turn_data.get("tool_executions", [])
            response = turn_data.get("response_text")

            lines.append("")
            lines.append(f"## Turno {turn}/{self.max_turns}")
            lines.append(f"*{dur_ms:.0f}ms | "
                         f"{turn_usage.get('total_tokens', 0):,} tokens | "
                         f"finish: {finish}*")
            lines.append("")

            # Respuesta del agente (si hay)
            if response:
                lines.append("### Respuesta del agente")
                lines.append("")
                lines.append(response)
                lines.append("")

            # Tools usadas (si hay)
            if tool_execs:
                lines.append("### Herramientas")
                lines.append("")
                for te in tool_execs:
                    tool_num += 1
                    name = te.get("name", "?")
                    args = te.get("arguments", {})

                    # Args: nombre del param y valor completo
                    args_display = []
                    for k, v in args.items():
                        args_display.append(f"{k}: {v}")

                    lines.append(f"**{tool_num}. {name}**")
                    for ad in args_display:
                        lines.append(f"  {ad}")

                    # Resultado completo
                    result_str = str(te.get("result", ""))
                    lines.append(f"  → {result_str}")

                    if te.get("exception"):
                        lines.append(f"  ⚠ ERROR: {te['exception']}")
                    lines.append("")

            # Turno sin respuesta ni tools (raro, pero posible)
            if not response and not tool_execs:
                lines.append("*(sin respuesta ni herramientas en este turno)*")
                lines.append("")

        # Resultado final
        lines.append("---")
        lines.append("")
        lines.append("## Resultado Final")
        lines.append("")
        if result:
            for key, value in result.items():
                if isinstance(value, list):
                    lines.append(f"**{key}**:")
                    for item in value:
                        if isinstance(item, dict):
                            parts = [f"{k}: {v}" for k, v in item.items()]
                            lines.append(f"  - {', '.join(parts)}")
                        else:
                            lines.append(f"  - {item}")
                elif isinstance(value, dict):
                    lines.append(f"**{key}**:")
                    for k, v in value.items():
                        lines.append(f"  {k}: {v}")
                else:
                    lines.append(f"**{key}**: {value}")
        else:
            lines.append("*(sin resultado)*")

        return "\n".join(lines)

    def _sanitize_config(self) -> dict:
        """Retorna la config sin datos sensibles (API keys, service accounts)."""
        sensitive_keys = {"service_account_file", "api_key"}
        sanitized = {}
        for k, v in self.agent_config.items():
            if k in sensitive_keys:
                sanitized[k] = "***" if v else None
            else:
                sanitized[k] = v
        return sanitized

    def _build_debug_md(self, input_prompt: str, result: dict | None, trace: dict) -> str:
        """Genera el markdown de debug con todos los detalles."""
        config = self._sanitize_config()
        lines = []

        # Header
        lines.append("# Debug: Ejecución del Agente")
        lines.append("")

        # Config
        lines.append("## Configuración")
        lines.append("")
        lines.append(f"| Campo | Valor |")
        lines.append(f"|-------|-------|")
        for key in ["name", "model", "provider", "location", "temperature",
                     "max_tokens", "max_turns", "stop_tool", "system_prompt",
                     "references_version", "capabilities"]:
            val = config.get(key, "—")
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            lines.append(f"| {key} | {val} |")
        lines.append("")

        # Resumen
        lines.append("## Resumen de ejecución")
        lines.append("")
        lines.append(f"| Métrica | Valor |")
        lines.append(f"|---------|-------|")
        lines.append(f"| Input | {input_prompt[:200]} |")
        lines.append(f"| Inicio | {trace['started_at']} |")
        lines.append(f"| Fin | {trace['completed_at']} |")
        lines.append(f"| Duración total | {trace['total_duration_s']}s |")
        lines.append(f"| Turnos usados | {trace['total_turns']}/{self.max_turns} |")
        lines.append(f"| Tool calls totales | {trace['total_tool_executions']} |")
        usage = trace["total_usage"]
        lines.append(f"| Tokens input | {usage.get('input_tokens', 0):,} |")
        lines.append(f"| Tokens output | {usage.get('output_tokens', 0):,} |")
        lines.append(f"| Tokens total | {usage.get('total_tokens', 0):,} |")
        lines.append("")

        # Uso por herramienta
        if trace.get("tool_usage_counts"):
            lines.append("### Uso por herramienta")
            lines.append("")
            for tool_name, count in sorted(trace["tool_usage_counts"].items()):
                lines.append(f"- **{tool_name}**: {count}")
            lines.append("")

        # Prompt template
        lines.append("### Prompt template")
        lines.append("")
        lines.append("```")
        lines.append(config.get("prompt_template", "—"))
        lines.append("```")
        lines.append("")

        # Turnos detallados
        lines.append("## Turnos detallados")
        lines.append("")

        for turn_data in trace["turns"]:
            turn_num = turn_data["turn"]
            turn_usage = turn_data.get("usage") or {}

            lines.append("---")
            lines.append("")
            lines.append(f"### Turno {turn_num}")
            lines.append("")

            # Metadatos del turno
            lines.append("| Métrica | Valor |")
            lines.append("|---------|-------|")
            lines.append(f"| Provider | {turn_data.get('provider', '?')} |")
            lines.append(f"| Model | {turn_data.get('model', '?')} |")
            lines.append(f"| Tokens in | {turn_usage.get('input_tokens', '?')} |")
            lines.append(f"| Tokens out | {turn_usage.get('output_tokens', '?')} |")
            lines.append(f"| Tokens total | {turn_usage.get('total_tokens', '?')} |")
            lines.append(f"| Finish reason | {turn_data.get('finish_reason', '?')} |")
            lines.append(f"| Duración | {turn_data.get('duration_ms', 0):.0f}ms |")
            lines.append(f"| Execution mode | {turn_data.get('execution_mode', '?')} |")
            lines.append(f"| Timestamp | {turn_data.get('timestamp', '?')} |")
            if turn_data.get("error"):
                lines.append(f"| **Error** | {turn_data['error']} |")
            lines.append("")

            # Run params (temperature, max_tokens, etc. efectivos del turno)
            run_params = turn_data.get("run_params")
            if run_params:
                lines.append("#### Parámetros del run")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(run_params, indent=2, default=str))
                lines.append("```")
                lines.append("")

            # Prompt completo enviado
            if turn_data.get("prompt_sent"):
                lines.append("#### Prompt enviado")
                lines.append("")
                lines.append("```")
                lines.append(turn_data["prompt_sent"])
                lines.append("```")
                lines.append("")

            # Respuesta del LLM
            if turn_data.get("response_text"):
                lines.append("#### Respuesta del LLM")
                lines.append("")
                lines.append(turn_data["response_text"])
                lines.append("")

            # Reasoning / thinking (si el modelo lo soporta)
            if turn_data.get("reasoning"):
                lines.append("#### Reasoning (thinking)")
                lines.append("")
                lines.append(turn_data["reasoning"])
                lines.append("")

            # LLM calls detallados
            llm_calls = turn_data.get("llm_calls", [])
            if llm_calls:
                lines.append(f"#### LLM calls ({len(llm_calls)})")
                lines.append("")
                for j, lc in enumerate(llm_calls, 1):
                    lines.append(f"**Call {j}**")
                    lines.append("")
                    if lc.get("response_id"):
                        lines.append(f"- Response ID: `{lc['response_id']}`")
                    if lc.get("response_model"):
                        lines.append(f"- Response model: `{lc['response_model']}`")
                    if lc.get("finish_reason"):
                        lines.append(f"- Finish reason: `{lc['finish_reason']}`")
                    if lc.get("usage"):
                        u = lc["usage"]
                        lines.append(f"- Tokens: in={u.get('input_tokens', '?')} out={u.get('output_tokens', '?')}")
                    if lc.get("reasoning_content"):
                        lines.append(f"- Reasoning: {lc['reasoning_content'][:500]}")
                    if lc.get("tool_calls_requested"):
                        lines.append(f"- Tool calls requested: {len(lc['tool_calls_requested'])}")
                        for tc in lc["tool_calls_requested"]:
                            lines.append(f"  - `{tc.get('name', '?')}`")
                    lines.append("")

            # Tool executions
            tool_execs = turn_data.get("tool_executions", [])
            if tool_execs:
                lines.append("#### Tool calls ejecutados")
                lines.append("")
                for i, te in enumerate(tool_execs, 1):
                    lines.append(f"**{i}. `{te['name']}`**")
                    if te.get("execution_mode"):
                        lines.append(f"  (execution_mode: {te['execution_mode']})")
                    lines.append("")
                    lines.append("Argumentos:")
                    lines.append("```json")
                    lines.append(json.dumps(te.get("arguments", {}), indent=2, ensure_ascii=False))
                    lines.append("```")
                    lines.append("")
                    lines.append("Resultado:")
                    lines.append("```")
                    lines.append(str(te.get("result", "N/A")))
                    lines.append("```")
                    if te.get("exception"):
                        lines.append("")
                        lines.append(f"**EXCEPTION**: {te['exception']}")
                    lines.append("")

            # Provider timing
            if turn_data.get("provider_timing"):
                lines.append("#### Provider timing")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(turn_data["provider_timing"], indent=2, default=str))
                lines.append("```")
                lines.append("")

        # Resultado final
        lines.append("---")
        lines.append("")
        lines.append("## Resultado Final")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(result, indent=2, ensure_ascii=False))
        lines.append("```")

        return "\n".join(lines)

    def _build_debug_json(self, input_prompt: str, result: dict | None, trace: dict) -> dict:
        """Genera un JSON estructurado para lectura humana.

        Similar al execution.json pero con resúmenes y sin el historial
        (que es redundante con los turnos).
        """
        config = self._sanitize_config()
        usage = trace["total_usage"]

        turns_summary = []
        for turn_data in trace["turns"]:
            turn_usage = turn_data.get("usage") or {}
            tool_execs = turn_data.get("tool_executions", [])
            turns_summary.append({
                "turn": turn_data["turn"],
                "provider": turn_data.get("provider"),
                "model": turn_data.get("model"),
                "execution_mode": turn_data.get("execution_mode"),
                "timestamp": turn_data.get("timestamp"),
                "duration_ms": turn_data.get("duration_ms"),
                "finish_reason": turn_data.get("finish_reason"),
                "error": turn_data.get("error"),
                "tokens": {
                    "input": turn_usage.get("input_tokens", 0),
                    "output": turn_usage.get("output_tokens", 0),
                    "total": turn_usage.get("total_tokens", 0),
                },
                "run_params": turn_data.get("run_params"),
                "prompt_sent": turn_data.get("prompt_sent"),
                "response_text": turn_data.get("response_text"),
                "reasoning": turn_data.get("reasoning"),
                "llm_calls": turn_data.get("llm_calls", []),
                "tool_calls": [
                    {
                        "tool": te["name"],
                        "arguments": te.get("arguments", {}),
                        "result": te.get("result"),
                        "exception": te.get("exception"),
                        "execution_mode": te.get("execution_mode"),
                    }
                    for te in tool_execs
                ],
                "provider_timing": turn_data.get("provider_timing"),
            })

        return {
            "config": config,
            "input": {"prompt": input_prompt},
            "summary": {
                "started_at": trace["started_at"],
                "completed_at": trace["completed_at"],
                "total_duration_s": trace["total_duration_s"],
                "total_turns": trace["total_turns"],
                "total_tool_executions": trace["total_tool_executions"],
                "tokens": {
                    "input": usage.get("input_tokens", 0),
                    "output": usage.get("output_tokens", 0),
                    "total": usage.get("total_tokens", 0),
                },
                "tool_usage_counts": trace.get("tool_usage_counts", {}),
            },
            "turns": turns_summary,
            "result": result,
        }
