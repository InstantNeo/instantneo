# New canonical imports
from .agent_capabilities import AgentCapabilities, ActivationRecord
from .tool_decorators import tool
from .capabilities_operations import CapabilitiesOperations
from .agent_skill import AgentSkill
from .skill_md_parser import SkillMdParser
from .navigation_helpers import create_navigation_tools, NAVIGATION_PROMPT

# Backward compatibility aliases
from .agent_capabilities import AgentCapabilities as SkillManager
from .tool_decorators import skill
from .capabilities_operations import CapabilitiesOperations as SkillManagerOperations
from .navigation_helpers import create_navigation_skills, SHELF_NAVIGATION_PROMPT

__all__ = [
    # New names
    'AgentCapabilities',
    'tool',
    'CapabilitiesOperations',
    'ActivationRecord',
    'create_navigation_tools',
    'NAVIGATION_PROMPT',
    # Backward compat
    'SkillManager',
    'skill',
    'SkillManagerOperations',
    'AgentSkill',
    'SkillMdParser',
    'create_navigation_skills',
    'SHELF_NAVIGATION_PROMPT',
]
