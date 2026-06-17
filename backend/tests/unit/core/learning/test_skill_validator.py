"""
Functional tests for SkillValidator YAML auto-fix logic.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from app.core.learning.skill_validator import SkillValidator


class TestYamlAutoFix:

    @pytest.fixture
    def temp_skill_md(self, tmp_path):
        """Factory to create temporary SKILL.md files."""
        def _create(content: str) -> Path:
            path = tmp_path / "SKILL.md"
            path.write_text(content, encoding="utf-8")
            return path
        return _create

    def test_valid_yaml_parsed_directly(self, temp_skill_md):
        """Valid YAML frontmatter → parsed directly without auto-fix."""
        content = """---
name: Test Skill
description: A valid description
namespace: roles
---

# Instructions
"""
        path = temp_skill_md(content)
        metadata, instructions = SkillValidator._parse_skill_md(path)
        
        assert metadata is not None
        assert metadata["name"] == "Test Skill"
        assert metadata["description"] == "A valid description"
        assert metadata["namespace"] == "roles"
        assert "# Instructions" in instructions

    def test_unquoted_colon_auto_fixed(self, temp_skill_md):
        """Unquoted value containing ': ' → auto-fixed and parsed."""
        content = """---
name: EvoLoop DevOps
description: End-to-end DevOps lifecycle: analyze project structure, verify configuration
namespace: roles
---

# Instructions
"""
        path = temp_skill_md(content)
        metadata, instructions = SkillValidator._parse_skill_md(path)
        
        assert metadata is not None
        assert metadata["name"] == "EvoLoop DevOps"
        assert "analyze project structure" in metadata["description"]
        assert metadata["namespace"] == "roles"

    def test_unquoted_hash_auto_fixed(self, temp_skill_md):
        """Unquoted value starting with '#' → auto-fixed and parsed."""
        content = """---
name: Test Skill
description: #important note about this skill
namespace: roles
---

# Instructions
"""
        path = temp_skill_md(content)
        metadata, instructions = SkillValidator._parse_skill_md(path)
        
        assert metadata is not None
        assert metadata["description"] == "#important note about this skill"

    def test_already_quoted_not_modified(self, temp_skill_md):
        """Already quoted values → left as-is."""
        content = """---
name: Test Skill
description: "Already quoted: with colon"
namespace: roles
---

# Instructions
"""
        path = temp_skill_md(content)
        metadata, instructions = SkillValidator._parse_skill_md(path)
        
        assert metadata is not None
        assert metadata["description"] == "Already quoted: with colon"

    def test_nested_mapping_not_modified(self, temp_skill_md):
        """Nested mapping values → not auto-quoted."""
        content = """---
name: Test Skill
parameters:
  customer:
    type: string
    description: The target customer
---

# Instructions
"""
        path = temp_skill_md(content)
        metadata, instructions = SkillValidator._parse_skill_md(path)
        
        assert metadata is not None
        assert "parameters" in metadata
        assert metadata["parameters"]["customer"]["type"] == "string"

    def test_list_items_not_modified(self, temp_skill_md):
        """List items → not auto-quoted."""
        content = """---
name: Test Skill
trigger_patterns:
  - "Deploy"
  - "Build"
---

# Instructions
"""
        path = temp_skill_md(content)
        metadata, instructions = SkillValidator._parse_skill_md(path)
        
        assert metadata is not None
        assert metadata["trigger_patterns"] == ["Deploy", "Build"]

    def test_irreparable_yaml_returns_none(self, temp_skill_md):
        """YAML that cannot be auto-fixed → returns None."""
        content = """---
name: Test Skill
description: {invalid: yaml: syntax: here}
  broken indentation
namespace: roles
---

# Instructions
"""
        path = temp_skill_md(content)
        metadata, instructions = SkillValidator._parse_skill_md(path)
        
        assert metadata is None

    def test_no_frontmatter_returns_none(self, temp_skill_md):
        """File without '---' frontmatter → returns None."""
        content = """# Just markdown

No YAML frontmatter here.
"""
        path = temp_skill_md(content)
        metadata, instructions = SkillValidator._parse_skill_md(path)
        
        assert metadata is None
        assert "No YAML frontmatter here." in instructions

    def test_fix_yaml_frontmatter_helper(self):
        """Test the _fix_yaml_frontmatter helper directly."""
        yaml_text = """name: Test Skill
description: End-to-end DevOps lifecycle: analyze project structure
namespace: roles
"""
        fixed = SkillValidator._fix_yaml_frontmatter(yaml_text)
        
        # Should have quoted the description
        assert 'description: "End-to-end DevOps lifecycle: analyze project structure"' in fixed
        
        # Should be parseable
        metadata = yaml.safe_load(fixed)
        assert metadata["description"] == "End-to-end DevOps lifecycle: analyze project structure"

    def test_fix_yaml_preserves_indentation(self):
        """Auto-fix preserves original indentation."""
        yaml_text = """  name: Test Skill
  description: End-to-end DevOps lifecycle: analyze
  namespace: roles
"""
        fixed = SkillValidator._fix_yaml_frontmatter(yaml_text)
        
        assert '  description: "End-to-end DevOps lifecycle: analyze"' in fixed
        assert '  name: Test Skill' in fixed
        assert '  namespace: roles' in fixed
