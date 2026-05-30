"""
Tests for SkillMdParser — pure-logic parsing, no LLM required.

Covers:
- parse_content: happy path, missing frontmatter, missing required fields,
  invalid YAML, allowed-tools splitting, optional fields
- parse_file / parse_folder: delegation + path propagation
- discover_folders: discovery of nested SKILL.md folders
"""
import pytest
from pathlib import Path
from instantneo.skills.skill_md_parser import SkillMdParser

# ────────────────────────────────────────────────────────────────────
# Shared fixtures
# ────────────────────────────────────────────────────────────────────

VALID_CONTENT = """\
---
name: my-skill
description: A test skill
license: MIT
allowed-tools: Bash Read Write
---
# Instructions
Do something useful.
"""

MINIMAL_CONTENT = """\
---
name: minimal
description: Minimal skill
---
Body text.
"""


# ════════════════════════════════════════════════════════════════════
# parse_content — happy paths
# ════════════════════════════════════════════════════════════════════

def test_parse_content_required_fields():
    skill = SkillMdParser.parse_content(VALID_CONTENT)
    assert skill.name == "my-skill"
    assert skill.description == "A test skill"


def test_parse_content_body_stripped():
    skill = SkillMdParser.parse_content(VALID_CONTENT)
    assert "Do something useful." in skill.instructions


def test_parse_content_optional_license():
    skill = SkillMdParser.parse_content(VALID_CONTENT)
    assert skill.license == "MIT"


def test_parse_content_allowed_tools_split():
    skill = SkillMdParser.parse_content(VALID_CONTENT)
    assert skill.allowed_tools == ["Bash", "Read", "Write"]


def test_parse_content_no_allowed_tools_returns_none():
    skill = SkillMdParser.parse_content(MINIMAL_CONTENT)
    assert skill.allowed_tools is None


def test_parse_content_no_license_returns_none():
    skill = SkillMdParser.parse_content(MINIMAL_CONTENT)
    assert skill.license is None


def test_parse_content_skill_path_propagated(tmp_path):
    skill = SkillMdParser.parse_content(MINIMAL_CONTENT, skill_path=tmp_path)
    assert skill.skill_path == tmp_path


def test_parse_content_skill_path_none_by_default():
    skill = SkillMdParser.parse_content(MINIMAL_CONTENT)
    assert skill.skill_path is None


# ════════════════════════════════════════════════════════════════════
# parse_content — error paths
# ════════════════════════════════════════════════════════════════════

def test_parse_content_no_frontmatter_raises():
    with pytest.raises(ValueError, match="frontmatter YAML"):
        SkillMdParser.parse_content("# No frontmatter\nJust body text")


def test_parse_content_missing_name_raises():
    content = "---\ndescription: A description\n---\nBody"
    with pytest.raises(ValueError, match="name"):
        SkillMdParser.parse_content(content)


def test_parse_content_empty_name_raises():
    content = "---\nname: \ndescription: A description\n---\nBody"
    with pytest.raises(ValueError, match="name"):
        SkillMdParser.parse_content(content)


def test_parse_content_missing_description_raises():
    content = "---\nname: test\n---\nBody"
    with pytest.raises(ValueError, match="description"):
        SkillMdParser.parse_content(content)


def test_parse_content_invalid_yaml_raises():
    # Unclosed bracket makes invalid YAML
    content = "---\nname: [\ninvalid: yaml here\n---\nBody"
    with pytest.raises(ValueError, match="YAML"):
        SkillMdParser.parse_content(content)


# ════════════════════════════════════════════════════════════════════
# parse_file
# ════════════════════════════════════════════════════════════════════

def test_parse_file_reads_content(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(VALID_CONTENT, encoding="utf-8")
    skill = SkillMdParser.parse_file(str(skill_md))
    assert skill.name == "my-skill"


def test_parse_file_sets_skill_path_to_parent(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(MINIMAL_CONTENT, encoding="utf-8")
    skill = SkillMdParser.parse_file(str(skill_md))
    assert skill.skill_path == tmp_path


def test_parse_file_not_found_raises():
    with pytest.raises(FileNotFoundError):
        SkillMdParser.parse_file("/nonexistent/path/SKILL.md")


# ════════════════════════════════════════════════════════════════════
# parse_folder
# ════════════════════════════════════════════════════════════════════

def test_parse_folder_reads_skill_md(tmp_path):
    (tmp_path / "SKILL.md").write_text(MINIMAL_CONTENT, encoding="utf-8")
    skill = SkillMdParser.parse_folder(str(tmp_path))
    assert skill.name == "minimal"


def test_parse_folder_sets_skill_path(tmp_path):
    (tmp_path / "SKILL.md").write_text(MINIMAL_CONTENT, encoding="utf-8")
    skill = SkillMdParser.parse_folder(str(tmp_path))
    assert skill.skill_path == tmp_path


def test_parse_folder_no_skill_md_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        SkillMdParser.parse_folder(str(tmp_path))


# ════════════════════════════════════════════════════════════════════
# discover_folders
# ════════════════════════════════════════════════════════════════════

def test_discover_folders_finds_skill_dirs(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(VALID_CONTENT, encoding="utf-8")

    discoveries = SkillMdParser.discover_folders(str(tmp_path))
    assert len(discoveries) == 1
    assert discoveries[0]["name"] == "my-skill"


def test_discover_folders_ignores_non_skill_dirs(tmp_path):
    (tmp_path / "no-skill-here").mkdir()
    skill_dir = tmp_path / "has-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(MINIMAL_CONTENT, encoding="utf-8")

    discoveries = SkillMdParser.discover_folders(str(tmp_path))
    assert len(discoveries) == 1
    assert discoveries[0]["name"] == "minimal"


def test_discover_folders_includes_path_and_type(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(VALID_CONTENT, encoding="utf-8")

    discoveries = SkillMdParser.discover_folders(str(tmp_path))
    d = discoveries[0]
    assert "path" in d
    assert d["type"] == "skill_folder"
    assert d["description"] == "A test skill"


def test_discover_folders_empty_root(tmp_path):
    assert SkillMdParser.discover_folders(str(tmp_path)) == []


def test_discover_folders_multiple_skills(tmp_path):
    for i in range(3):
        d = tmp_path / f"skill-{i}"
        d.mkdir()
        content = f"---\nname: skill-{i}\ndescription: Skill {i}\n---\nBody"
        (d / "SKILL.md").write_text(content, encoding="utf-8")

    discoveries = SkillMdParser.discover_folders(str(tmp_path))
    assert len(discoveries) == 3
    names = {d["name"] for d in discoveries}
    assert names == {"skill-0", "skill-1", "skill-2"}
