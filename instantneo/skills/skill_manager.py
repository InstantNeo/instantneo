# Backward compatibility stub - imports from agent_capabilities
from .agent_capabilities import (
    AgentCapabilities,
    AgentCapabilities as SkillManager,
    CapabilityLoader,
    CapabilityLoader as SkillLoader,
    ActivationRecord,
)

__all__ = ['SkillManager', 'AgentCapabilities', 'SkillLoader', 'CapabilityLoader', 'ActivationRecord']
