from typing import Dict, Any

#############################################
#   SESSION TRACKING UTILS FOR INSTANTNEO   #
#############################################

def get_config_snapshot(agent) -> Dict[str, Any]:
    """Devuelve un snapshot limpio y seguro de la configuración del agente."""
    return {
        "provider": agent.config.provider,
        "model": agent.config.model,
        "role_setup": agent.config.role_setup,
        "temperature": agent.config.temperature,
        "max_tokens": agent.config.max_tokens,
        "presence_penalty": agent.config.presence_penalty,
        "frequency_penalty": agent.config.frequency_penalty,
        "stop": agent.config.stop,
        "logit_bias": agent.config.logit_bias,
        "seed": agent.config.seed,
        "stream": agent.config.stream,
        "skills": agent.get_skill_names(),
        "image_detail": agent.config.image_detail,
        "images": "[...]" if agent.config.images else None
    }


def get_run_params_snapshot(run_params) -> Dict[str, Any]:
    """Devuelve un snapshot limpio de los parámetros de ejecución."""
    return {
        "prompt": run_params.prompt,
        "execution_mode": run_params.execution_mode,
        "async_execution": run_params.async_execution,
        "return_full_response": run_params.return_full_response,
        "temperature": run_params.temperature,
        "max_tokens": run_params.max_tokens,
        "skills": run_params.skills,
        "images": run_params.images,
        "image_detail": run_params.image_detail,
        "additional_params": run_params.additional_params,
    }