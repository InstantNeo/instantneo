"""
Tests for backward-compatibility stub modules.

Each stub is just a re-export from the canonical module. These tests ensure:
1. The stubs are importable (no broken imports).
2. Aliased names point to the same objects as the originals.
"""

# ════════════════════════════════════════════════════════════════════
# shelf_helpers.py
# ════════════════════════════════════════════════════════════════════

def test_shelf_helpers_exports_navigation_tools():
    from instantneo.skills.shelf_helpers import (
        create_navigation_tools,
        create_navigation_skills,  # alias
        NAVIGATION_PROMPT,
        SHELF_NAVIGATION_PROMPT,   # alias
    )
    assert callable(create_navigation_tools)
    assert create_navigation_skills is create_navigation_tools
    assert isinstance(NAVIGATION_PROMPT, str)
    assert SHELF_NAVIGATION_PROMPT is NAVIGATION_PROMPT


# ════════════════════════════════════════════════════════════════════
# skill_decorators.py
# ════════════════════════════════════════════════════════════════════

def test_skill_decorators_exports_tool_and_skill():
    from instantneo.skills.skill_decorators import skill, tool
    from instantneo.skills.tool_decorators import tool as canonical_tool, skill as canonical_skill
    assert tool is canonical_tool
    assert skill is canonical_skill


# ════════════════════════════════════════════════════════════════════
# skill_manager.py
# ════════════════════════════════════════════════════════════════════

def test_skill_manager_exports_agent_capabilities():
    from instantneo.skills.skill_manager import (
        AgentCapabilities,
        SkillManager,
        CapabilityLoader,
        SkillLoader,
        ActivationRecord,
    )
    from instantneo.skills.agent_capabilities import (
        AgentCapabilities as Canonical,
        CapabilityLoader as CanonicalLoader,
        ActivationRecord as CanonicalRecord,
    )
    assert AgentCapabilities is Canonical
    assert SkillManager is Canonical
    assert CapabilityLoader is CanonicalLoader
    assert SkillLoader is CanonicalLoader
    assert ActivationRecord is CanonicalRecord


# ════════════════════════════════════════════════════════════════════
# skill_manager_operations.py
# ════════════════════════════════════════════════════════════════════

def test_skill_manager_operations_exports():
    from instantneo.skills.skill_manager_operations import (
        CapabilitiesOperations,
        SkillManagerOperations,
    )
    from instantneo.skills.capabilities_operations import (
        CapabilitiesOperations as Canonical,
    )
    assert CapabilitiesOperations is Canonical
    assert SkillManagerOperations is Canonical


# ════════════════════════════════════════════════════════════════════
# utils/skill_utils.py
# ════════════════════════════════════════════════════════════════════

def test_skill_utils_exports():
    from instantneo.utils.skill_utils import python_type_to_string, format_tool
    from instantneo.utils.tool_utils import python_type_to_string as c1, format_tool as c2
    assert python_type_to_string is c1
    assert format_tool is c2
