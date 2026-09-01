"""Unit coverage for SkillValidator (folder structure + SKILL.md parsing)."""

from __future__ import annotations

from pathlib import Path

from app.core.learning.skills.validator import SkillValidator

VALID_MD = """---
name: test-skill
description: A test skill
namespace: os/test
---
# Instructions

Do the thing.
"""


def _write_skill_md(folder: Path, content: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    md = folder / "SKILL.md"
    md.write_text(content, encoding="utf-8")
    return md


class TestValidateFolder:
    def test_missing_directory(self, tmp_path):
        result = SkillValidator.validate_folder(tmp_path / "nope")
        assert result.is_valid is False
        assert result.status == "error"

    def test_missing_skill_md(self, tmp_path):
        folder = tmp_path / "s"
        folder.mkdir()
        result = SkillValidator.validate_folder(folder)
        assert result.is_valid is False
        assert any("SKILL.md" in e for e in result.errors)

    def test_healthy(self, tmp_path):
        folder = tmp_path / "s"
        _write_skill_md(folder, VALID_MD)
        result = SkillValidator.validate_folder(folder)
        assert result.is_valid is True
        assert result.status == "healthy"
        assert result.metadata["name"] == "test-skill"

    def test_missing_name_is_error(self, tmp_path):
        folder = tmp_path / "s"
        _write_skill_md(
            folder, "---\ndescription: no name\n---\n# Instructions\n"
        )
        result = SkillValidator.validate_folder(folder)
        assert result.is_valid is False
        assert any("name" in e for e in result.errors)

    def test_missing_description_is_warning(self, tmp_path):
        folder = tmp_path / "s"
        _write_skill_md(folder, "---\nname: x\n---\n")
        result = SkillValidator.validate_folder(folder)
        assert result.is_valid is True
        assert result.status == "warning"

    def test_clutter_warns(self, tmp_path):
        folder = tmp_path / "s"
        _write_skill_md(folder, VALID_MD)
        (folder / "README.md").write_text("readme")
        result = SkillValidator.validate_folder(folder)
        assert result.is_valid is True
        assert result.status == "warning"
        assert any("README.md" in w for w in result.warnings)


class TestParseSkillMd:
    def test_parses_frontmatter(self, tmp_path):
        md = _write_skill_md(tmp_path / "s", VALID_MD)
        metadata, instructions = SkillValidator._parse_skill_md(md)
        assert metadata["name"] == "test-skill"
        assert "Do the thing" in instructions

    def test_no_frontmatter(self, tmp_path):
        md = _write_skill_md(tmp_path / "s", "# Just instructions\n")
        metadata, instructions = SkillValidator._parse_skill_md(md)
        assert metadata is None
        assert "Just instructions" in instructions

    def test_auto_fixes_broken_yaml(self, tmp_path):
        # "#" value parses as None on the first pass → auto-fix quotes it
        md = _write_skill_md(
            tmp_path / "s",
            "---\nname: # comment here\ndescription: d\n---\n# Instructions\n",
        )
        metadata, _ = SkillValidator._parse_skill_md(md)
        assert metadata is not None
        assert metadata["name"] == "# comment here"

    def test_unparseable_returns_none(self, tmp_path):
        md = _write_skill_md(tmp_path / "s", "---\n: : : bad\nyaml: [unclosed\n---\n")
        metadata, instructions = SkillValidator._parse_skill_md(md)
        assert metadata is None


class TestFixYamlFrontmatter:
    def test_quotes_colon_values(self):
        # "install step: 1" is not a nested-mapping shape → gets quoted
        fixed = SkillValidator._fix_yaml_frontmatter("name: install step: 1\n")
        assert 'name: "install step: 1"' in fixed

    def test_quotes_hash_values(self):
        fixed = SkillValidator._fix_yaml_frontmatter("name: # comment\n")
        assert 'name: "# comment"' in fixed

    def test_leaves_valid_lines(self):
        text = 'name: ok\ndescription: plain\ntrigger_patterns:\n  - a\n'
        assert SkillValidator._fix_yaml_frontmatter(text) == text
