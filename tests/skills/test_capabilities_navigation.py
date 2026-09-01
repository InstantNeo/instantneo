"""
Tests for AgentCapabilities navigation layer:
  discover, activate, deactivate, get_active_context, get_active_tools,
  clear_active, find/_search_recursive, _find_item, _resolve_path.

All tests use in-memory skill folders (via SKILL.md in tmp_path) or
direct tool registration — no real LLM calls.
"""
import pytest
from instantneo.skills.agent_capabilities import AgentCapabilities
from instantneo.skills.tool_decorators import tool


# ── Shared tools ─────────────────────────────────────────────────

@tool(description="Nav-test tool A")
def _nav_tool_a(x: int) -> int:
    return x


@tool(description="Nav-test tool B")
def _nav_tool_b(y: str) -> str:
    return y


# ── SKILL.md helpers ─────────────────────────────────────────────

def _make_skill_folder(root, name: str, description: str = "A skill") -> str:
    """Create a minimal SKILL.md folder inside root, return the folder path."""
    folder = root / name
    folder.mkdir(exist_ok=True)
    content = f"---\nname: {name}\ndescription: {description}\n---\n# Instructions\nDo the thing.\n"
    (folder / "SKILL.md").write_text(content, encoding="utf-8")
    return str(folder)


# ════════════════════════════════════════════════════════════════════
# discover
# ════════════════════════════════════════════════════════════════════

def test_discover_empty_returns_empty():
    caps = AgentCapabilities(skills=[_nav_tool_a])
    # discover only shows skill_folders and managers, not direct tools
    assert caps.discover() == []


def test_discover_shows_skill_folders(tmp_path):
    caps = AgentCapabilities()
    caps.load_skills.from_skill_folder(_make_skill_folder(tmp_path, "my-skill"))
    items = caps.discover()
    assert len(items) == 1
    assert items[0]["name"] == "my-skill"
    assert items[0]["type"] == "skill_folder"


def test_discover_shows_sub_managers():
    sub = AgentCapabilities(name="sub-mgr", description="Sub manager")
    caps = AgentCapabilities()
    caps.load_skills.from_manager(sub)
    items = caps.discover()
    assert len(items) == 1
    assert items[0]["name"] == "sub-mgr"
    assert items[0]["type"] == "manager"


def test_discover_with_path_delegates(tmp_path):
    sub = AgentCapabilities(name="sub", description="Sub")
    sub.load_skills.from_skill_folder(_make_skill_folder(tmp_path, "inner-skill"))
    caps = AgentCapabilities()
    caps.load_skills.from_manager(sub)
    items = caps.discover("sub")
    assert len(items) == 1
    assert items[0]["name"] == "inner-skill"


def test_discover_with_nonexistent_path_returns_empty():
    caps = AgentCapabilities()
    assert caps.discover("nonexistent/path") == []


# ════════════════════════════════════════════════════════════════════
# activate / deactivate
# ════════════════════════════════════════════════════════════════════

def test_activate_skill_folder(tmp_path):
    caps = AgentCapabilities()
    caps.load_skills.from_skill_folder(_make_skill_folder(tmp_path, "target-skill"))
    result = caps.activate("target-skill")
    assert result["name"] == "target-skill"
    assert result["type"] == "skill_folder"
    assert "instructions" in result


def test_activate_nonexistent_raises():
    caps = AgentCapabilities()
    with pytest.raises(ValueError):
        caps.activate("ghost")


def test_activate_direct_tool():
    caps = AgentCapabilities(skills=[_nav_tool_a])
    result = caps.activate("_nav_tool_a")
    assert result["type"] == "skill"
    assert "_nav_tool_a" in result["skills_loaded"]


def test_activate_records_active_item(tmp_path):
    caps = AgentCapabilities()
    caps.load_skills.from_skill_folder(_make_skill_folder(tmp_path, "active-skill"))
    caps.activate("active-skill")
    assert "active-skill" in caps._active_items


def test_activate_manager():
    sub = AgentCapabilities(
        name="active-sub", description="Sub", global_instructions="Follow sub rules"
    )
    caps = AgentCapabilities()
    caps.load_skills.from_manager(sub)
    result = caps.activate("active-sub")
    assert result["type"] == "manager"
    assert result["description"] == "Sub"


def test_deactivate_success(tmp_path):
    caps = AgentCapabilities()
    caps.load_skills.from_skill_folder(_make_skill_folder(tmp_path, "deact-skill"))
    caps.activate("deact-skill")
    success = caps.deactivate("deact-skill")
    assert success is True
    assert "deact-skill" not in caps._active_items


def test_deactivate_not_active_returns_false():
    caps = AgentCapabilities()
    assert caps.deactivate("not-there") is False


# ════════════════════════════════════════════════════════════════════
# get_active_context / get_active_tools
# ════════════════════════════════════════════════════════════════════

def test_get_active_context_empty():
    caps = AgentCapabilities()
    assert caps.get_active_context() == ""


def test_get_active_context_after_activate(tmp_path):
    caps = AgentCapabilities()
    caps.load_skills.from_skill_folder(
        _make_skill_folder(tmp_path, "ctx-skill", description="Context skill")
    )
    caps.activate("ctx-skill")
    ctx = caps.get_active_context()
    assert "ctx-skill" in ctx
    assert "Do the thing." in ctx


def test_get_active_tools_after_activate():
    caps = AgentCapabilities(skills=[_nav_tool_b])
    caps.activate("_nav_tool_b")
    active_tools = caps.get_active_tools()
    assert "_nav_tool_b" in active_tools


def test_get_active_tools_empty():
    caps = AgentCapabilities()
    assert caps.get_active_tools() == {}


# ════════════════════════════════════════════════════════════════════
# clear_active
# ════════════════════════════════════════════════════════════════════

def test_clear_active(tmp_path):
    caps = AgentCapabilities()
    caps.load_skills.from_skill_folder(_make_skill_folder(tmp_path, "clr-skill"))
    caps.activate("clr-skill")
    assert "clr-skill" in caps._active_items
    caps.clear_active()
    assert caps._active_items == {}


# ════════════════════════════════════════════════════════════════════
# find / _search_recursive
# ════════════════════════════════════════════════════════════════════

def test_find_tool_by_name():
    caps = AgentCapabilities(skills=[_nav_tool_a])
    results = caps.find("_nav_tool_a")
    assert any(r["name"] == "_nav_tool_a" for r in results)


def test_find_skill_folder(tmp_path):
    caps = AgentCapabilities()
    caps.load_skills.from_skill_folder(_make_skill_folder(tmp_path, "search-skill"))
    results = caps.find("search-skill")
    assert any(r["type"] == "skill_folder" for r in results)


def test_find_partial_match():
    caps = AgentCapabilities(skills=[_nav_tool_a, _nav_tool_b])
    results = caps.find("_nav_tool")
    assert len(results) >= 2


def test_find_no_match():
    caps = AgentCapabilities()
    assert caps.find("absolutely_nothing_here") == []


def test_find_in_sub_manager():
    sub = AgentCapabilities(name="sub-finder", description="Sub")
    sub.register_tool(_nav_tool_a)
    caps = AgentCapabilities()
    caps.load_skills.from_manager(sub)
    results = caps.find("_nav_tool_a")
    assert len(results) >= 1
    # path should include the sub-manager name
    assert any("sub-finder" in r["path"] for r in results)


# ════════════════════════════════════════════════════════════════════
# _find_item
# ════════════════════════════════════════════════════════════════════

def test_find_item_direct_tool():
    caps = AgentCapabilities(skills=[_nav_tool_a])
    item, item_type = caps._find_item("_nav_tool_a")
    assert item is _nav_tool_a
    assert item_type == "skill"


def test_find_item_skill_folder(tmp_path):
    caps = AgentCapabilities()
    caps.load_skills.from_skill_folder(_make_skill_folder(tmp_path, "findable-skill"))
    item, item_type = caps._find_item("findable-skill")
    assert item_type == "skill_folder"


def test_find_item_manager():
    sub = AgentCapabilities(name="findable-mgr", description="Sub")
    caps = AgentCapabilities()
    caps.load_skills.from_manager(sub)
    item, item_type = caps._find_item("findable-mgr")
    assert item is sub
    assert item_type == "manager"


def test_find_item_not_found():
    caps = AgentCapabilities()
    item, item_type = caps._find_item("ghost")
    assert item is None
    assert item_type is None


def test_find_item_path_with_slash():
    sub = AgentCapabilities(name="my-sub", description="Sub")
    sub.register_tool(_nav_tool_a)
    caps = AgentCapabilities()
    caps.load_skills.from_manager(sub)
    item, item_type = caps._find_item("my-sub/_nav_tool_a")
    assert item is _nav_tool_a
    assert item_type == "skill"


def test_find_item_ambiguous_raises():
    # Same tool name in two different sub-managers → ambiguous
    sub_a = AgentCapabilities(name="sub-a", description="A")
    sub_a.register_tool(_nav_tool_a)
    sub_b = AgentCapabilities(name="sub-b", description="B")
    sub_b.register_tool(_nav_tool_a)  # same function name

    caps = AgentCapabilities()
    caps.load_skills.from_manager(sub_a)
    caps.load_skills.from_manager(sub_b)

    with pytest.raises(ValueError, match="múltiples ubicaciones"):
        caps._find_item("_nav_tool_a")


# ════════════════════════════════════════════════════════════════════
# _resolve_path
# ════════════════════════════════════════════════════════════════════

def test_resolve_path_to_manager():
    sub = AgentCapabilities(name="sub-resolve", description="Sub")
    caps = AgentCapabilities()
    caps.load_skills.from_manager(sub)
    result = caps._resolve_path("sub-resolve")
    assert result is sub


def test_resolve_path_to_tool():
    caps = AgentCapabilities(skills=[_nav_tool_a])
    result = caps._resolve_path("_nav_tool_a")
    assert result is _nav_tool_a


def test_resolve_path_nonexistent_returns_none():
    caps = AgentCapabilities()
    assert caps._resolve_path("ghost") is None
