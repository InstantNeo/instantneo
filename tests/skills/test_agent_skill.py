"""
Tests for AgentSkill dataclass methods.

Covers:
- discovery_info property
- get_instructions method
- get_file: reads file, uses cache, nonexistent → None, no skill_path → None
- list_files: all files (excludes SKILL.md), specific subdir, no skill_path
- get_file_path: found, not found, no skill_path
- __repr__
"""
import pytest
from pathlib import Path
from instantneo.skills.agent_skill import AgentSkill


# ════════════════════════════════════════════════════════════════════
# discovery_info
# ════════════════════════════════════════════════════════════════════

def test_discovery_info_fields():
    skill = AgentSkill(name="test-skill", description="Does X", instructions="Step 1")
    info = skill.discovery_info
    assert info["name"] == "test-skill"
    assert info["description"] == "Does X"
    assert info["type"] == "skill_folder"


def test_discovery_info_does_not_include_instructions():
    skill = AgentSkill(name="s", description="d", instructions="secret instructions")
    assert "instructions" not in skill.discovery_info


# ════════════════════════════════════════════════════════════════════
# get_instructions
# ════════════════════════════════════════════════════════════════════

def test_get_instructions_returns_body():
    skill = AgentSkill(name="s", description="d", instructions="Step 1\nStep 2")
    assert skill.get_instructions() == "Step 1\nStep 2"


def test_get_instructions_empty_string():
    skill = AgentSkill(name="s", description="d", instructions="")
    assert skill.get_instructions() == ""


# ════════════════════════════════════════════════════════════════════
# get_file
# ════════════════════════════════════════════════════════════════════

def test_get_file_reads_existing_file(tmp_path):
    (tmp_path / "run.py").write_text("print('hello')", encoding="utf-8")
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    assert skill.get_file("run.py") == "print('hello')"


def test_get_file_caches_result(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("first", encoding="utf-8")
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    first = skill.get_file("run.py")
    # overwrite on disk — cache must return original
    script.write_text("second", encoding="utf-8")
    second = skill.get_file("run.py")
    assert first == second == "first"


def test_get_file_nonexistent_returns_none(tmp_path):
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    assert skill.get_file("ghost.py") is None


def test_get_file_no_skill_path_returns_none():
    skill = AgentSkill(name="s", description="d", instructions="x")
    assert skill.get_file("anything.py") is None


def test_get_file_nested_path(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "extract.py").write_text("# extract", encoding="utf-8")
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    assert skill.get_file("scripts/extract.py") == "# extract"


# ════════════════════════════════════════════════════════════════════
# list_files
# ════════════════════════════════════════════════════════════════════

def test_list_files_excludes_skill_md(tmp_path):
    (tmp_path / "SKILL.md").write_text("---\nname: x\n---")
    (tmp_path / "helper.py").write_text("x")
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    files = skill.list_files()
    assert not any("SKILL.md" in f for f in files)
    assert any("helper.py" in f for f in files)


def test_list_files_includes_all_non_skill_md(tmp_path):
    (tmp_path / "a.py").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    files = skill.list_files()
    assert len(files) == 2


def test_list_files_subdir_only(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("x")
    (scripts / "helper.py").write_text("y")
    (tmp_path / "README.md").write_text("docs")
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    files = skill.list_files("scripts")
    assert len(files) == 2
    assert all(f.startswith("scripts/") for f in files)


def test_list_files_subdir_nonexistent_returns_empty(tmp_path):
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    assert skill.list_files("nonexistent") == []


def test_list_files_no_skill_path_returns_empty():
    skill = AgentSkill(name="s", description="d", instructions="x")
    assert skill.list_files() == []


def test_list_files_no_skill_path_subdir_returns_empty():
    skill = AgentSkill(name="s", description="d", instructions="x")
    assert skill.list_files("scripts") == []


# ════════════════════════════════════════════════════════════════════
# get_file_path
# ════════════════════════════════════════════════════════════════════

def test_get_file_path_returns_path(tmp_path):
    script = tmp_path / "run.py"
    script.write_text("x")
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    result = skill.get_file_path("run.py")
    assert result == script


def test_get_file_path_nonexistent_returns_none(tmp_path):
    skill = AgentSkill(name="s", description="d", instructions="x", skill_path=tmp_path)
    assert skill.get_file_path("ghost.py") is None


def test_get_file_path_no_skill_path_returns_none():
    skill = AgentSkill(name="s", description="d", instructions="x")
    assert skill.get_file_path("run.py") is None


# ════════════════════════════════════════════════════════════════════
# __repr__
# ════════════════════════════════════════════════════════════════════

def test_repr_contains_name():
    skill = AgentSkill(name="my-skill", description="d", instructions="x")
    assert "my-skill" in repr(skill)


def test_repr_is_string():
    skill = AgentSkill(name="s", description="d", instructions="x")
    assert isinstance(repr(skill), str)
