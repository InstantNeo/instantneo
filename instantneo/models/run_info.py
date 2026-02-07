"""
Modelos de datos para metadata de ejecución de InstantNeo.

Contiene las dataclasses que capturan información sobre cada run():
- SkillExecution: Detalle de cada skill ejecutado
- LLMCall: Detalle de cada llamada al LLM
- RunInfo: Información completa de un run()
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillExecution:
    """
    Información sobre la ejecución de un skill individual.

    Attributes:
        name: Nombre del skill ejecutado
        arguments: Argumentos pasados al skill (dict, no JSON string)
        result: Resultado retornado por el skill
        exception: Mensaje de error si el skill falló
        execution_mode: Modo de ejecución usado (wait_response, execution_only, get_args)
    """
    name: str
    arguments: Dict[str, Any]
    result: Any = None
    exception: Optional[str] = None
    execution_mode: str = "wait_response"


@dataclass
class LLMCall:
    """
    Información sobre una llamada individual al LLM.

    Attributes:
        messages_sent: Messages enviados al LLM
        response_content: Texto de respuesta del LLM
        finish_reason: Razón de finalización (stop, length, tool_calls, etc.)
        tool_calls_requested: Tool calls que pidió el LLM
        usage: Tokens usados {input_tokens, output_tokens, total_tokens}
        response_id: ID de respuesta del provider
        response_model: Modelo que respondió
        raw_response: StandardResponse completo
    """
    messages_sent: List[Dict] = field(default_factory=list)
    response_content: Optional[str] = None
    finish_reason: Optional[str] = None
    tool_calls_requested: List[Dict] = field(default_factory=list)
    usage: Optional[Dict[str, int]] = None
    response_id: Optional[str] = None
    response_model: Optional[str] = None
    raw_response: Any = None


@dataclass
class RunInfo:
    """
    Información completa sobre una ejecución de run().

    Captura toda la metadata necesaria para logging, debugging,
    pricing y observabilidad.

    Attributes:
        provider: Proveedor LLM usado
        model: Modelo usado
        prompt: Prompt del usuario
        execution_mode: Modo de ejecución (wait_response, execution_only, get_args)
        stream: Si se usó streaming
        timestamp: Marca de tiempo ISO format
        messages_sent: Messages enviados al LLM
        response_content: Contenido de la respuesta final
        finish_reason: Razón de finalización
        llm_calls: Lista de llamadas al LLM (1 por ahora, lista para futuro multi-turn)
        skill_executions: Skills ejecutados durante el run
        usage: Tokens agregados {input_tokens, output_tokens, total_tokens}
        run_params: Snapshot de los parámetros resueltos para este run
        error: Mensaje de error si el run falló
        duration_ms: Duración total del run en milisegundos
        provider_timing: Timing específico del provider (Cerebras time_info, Groq prompt_time, etc.)
    """
    # Instancia
    provider: str
    model: str

    # Input
    prompt: str
    execution_mode: str
    stream: bool
    timestamp: str

    # Messages enviados
    messages_sent: List[Dict] = field(default_factory=list)

    # Respuesta final
    response_content: Optional[str] = None
    finish_reason: Optional[str] = None

    # Detalle
    llm_calls: List[LLMCall] = field(default_factory=list)
    skill_executions: List[SkillExecution] = field(default_factory=list)

    # Tokens (agregado)
    usage: Optional[Dict[str, int]] = None

    # Config snapshot
    run_params: Optional[Dict] = None

    # Error
    error: Optional[str] = None

    # Timing
    duration_ms: Optional[float] = None
    provider_timing: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialización JSON-safe del RunInfo.

        Excluye raw_response de los LLMCalls para evitar objetos no serializables.
        """
        def _skill_exec_to_dict(se: SkillExecution) -> Dict[str, Any]:
            return {
                "name": se.name,
                "arguments": se.arguments,
                "result": _safe_serialize(se.result),
                "exception": se.exception,
                "execution_mode": se.execution_mode,
            }

        def _llm_call_to_dict(lc: LLMCall) -> Dict[str, Any]:
            return {
                "messages_sent": lc.messages_sent,
                "response_content": lc.response_content,
                "finish_reason": lc.finish_reason,
                "tool_calls_requested": lc.tool_calls_requested,
                "usage": lc.usage,
                "response_id": lc.response_id,
                "response_model": lc.response_model,
                # raw_response excluido intencionalmente
            }

        def _safe_serialize(obj: Any) -> Any:
            """Intenta serializar un objeto, fallback a str()."""
            if obj is None:
                return None
            if isinstance(obj, (str, int, float, bool)):
                return obj
            if isinstance(obj, (list, tuple)):
                return [_safe_serialize(item) for item in obj]
            if isinstance(obj, dict):
                return {k: _safe_serialize(v) for k, v in obj.items()}
            return str(obj)

        return {
            "provider": self.provider,
            "model": self.model,
            "prompt": self.prompt,
            "execution_mode": self.execution_mode,
            "stream": self.stream,
            "timestamp": self.timestamp,
            "messages_sent": self.messages_sent,
            "response_content": self.response_content,
            "finish_reason": self.finish_reason,
            "llm_calls": [_llm_call_to_dict(lc) for lc in self.llm_calls],
            "skill_executions": [_skill_exec_to_dict(se) for se in self.skill_executions],
            "usage": self.usage,
            "run_params": _safe_serialize(self.run_params),
            "error": self.error,
            "duration_ms": self.duration_ms,
            "provider_timing": self.provider_timing,
        }
