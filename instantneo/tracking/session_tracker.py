from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


class SessionTracker:
    """
    Tracker pasivo que sigue a una instancia de InstantNeo,
    registrando sesiones completas (únicas o en loop).
    """

    def __init__(self):
        self.sessions: List[Dict[str, Any]] = []
        self._current_session: Optional[Dict[str, Any]] = None
        self._attached_to: Optional[Any] = None
        self._step_counter: int = 0

    ##################
    #   Connection   #
    ##################

    def track(self, agent: Any):
        """Vincula este tracker a una instancia de InstantNeo."""
        self._attached_to = agent
        agent.tracker = self

    def detach(self):
        """Desvincula el tracker del agente. No borra historial."""
        if self._attached_to:
            self._attached_to.tracker = None
        self._attached_to = None
    
    ###############
    #   Session   #
    ###############

    def start_session(self, metadata: Optional[Dict[str, Any]] = None):
        """Inicia una nueva sesión de seguimiento."""
        if self._current_session is not None:
            raise RuntimeError("Ya hay una sesión activa. Llama a stop_session() primero.")

        self._current_session = {
            "start_time": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
            "steps": []
        }
        self._step_counter = 0

    def stop_session(self, metadata: Optional[Dict[str, Any]] = None):
            """Finaliza la sesión activa y la guarda en el historial."""
            if self._current_session is None:
                raise RuntimeError("No hay sesión activa para detener.")

            self._before_stop()

            self._current_session["end_time"] = datetime.now(timezone.utc).isoformat()
            if metadata:
                self._current_session["metadata"].update(metadata)

            self.sessions.append(self._current_session)
            self._current_session = None

            self._after_stop()

    def _before_stop(self):
            pass

    def _after_stop(self):
            pass
    
    def has_active_session(self) -> bool:
        return self._current_session is not None
    
    ############
    #   Logs   #
    ############
    
    def log(self,input: Any,output: Any,origin: str,skills: Optional[List[str]] = None,exception: Optional[str] = None,metadata: Optional[Dict[str, Any]] = None, **kwargs):
        """Registra un paso dentro de la sesión activa."""
        if self._current_session is None:
            raise RuntimeError("No hay sesión activa. Llama a start_session() antes de log().")

        step = {
            "step_id": self._step_counter,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input": input,
            "output": output,
            "origin": origin,
            "skills": skills or [],
            "exception": exception,
            "metadata": metadata or {}
        }
        step.update(kwargs)
        self._step_counter += 1
        self._current_session["steps"].append(step)

    def log_skill_execution(
        self,
        skill_name: str,
        arguments: Dict[str, Any],
        result: Any = None,
        exception: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Registra la ejecución de una skill en la sesión activa."""
        if self._current_session is None:
            raise RuntimeError("No hay sesión activa para loggear.")

        self._current_session["steps"].append({
            "step_id": self._step_counter,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "skill_execution",
            "skill_name": skill_name,
            "arguments": arguments,
            "result": result,
            "exception": exception,
            "metadata": metadata or {},
        })
        self._step_counter += 1
    ###################
    #   Access Data   #
    ###################  

    def get_last_session(self) -> Optional[Dict[str, Any]]:
        return self.sessions[-1] if self.sessions else None

    def get_last_step(self) -> Optional[Dict[str, Any]]:
        if self._current_session and self._current_session["steps"]:
            return self._current_session["steps"][-1]
        elif self.sessions and self.sessions[-1]["steps"]:
            return self.sessions[-1]["steps"][-1]
        return None

    def get_all_steps(self) -> List[Dict[str, Any]]:
        steps = []
        for session in self.sessions:
            steps.extend(session["steps"])
        if self._current_session:
            steps.extend(self._current_session["steps"])
        return steps

    def reset(self):
        self.sessions.clear()
        self._current_session = None