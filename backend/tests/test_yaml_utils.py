"""Tests for YAML utilities."""

import pytest
from app.utils.yaml import (
    safe_yaml_loads,
    safe_yaml_dumps,
    macro_from_yaml,
    macro_to_yaml,
    validate_macro_yaml,
    YAMLError
)


class TestYAMLParsing:
    """Test YAML parsing functions."""
    
    def test_parse_simple_macro(self):
        yaml_content = """
steps:
  - type: action
    event_type: click
    source: dom
    target_selector: ".btn"
"""
        result = macro_from_yaml(yaml_content)
        assert len(result) == 1
        assert result[0]["type"] == "action"
        assert result[0]["event_type"] == "click"
    
    def test_parse_nested_structure(self):
        yaml_content = """
steps:
  - type: if
    condition:
      type: element_exists
      target_selector: ".modal"
    then_steps:
      - type: action
        event_type: click
        target_selector: ".close"
"""
        result = macro_from_yaml(yaml_content)
        assert result[0]["type"] == "if"
        assert len(result[0]["then_steps"]) == 1
    
    def test_parse_with_metadata(self):
        yaml_content = """
version: "1.0"
metadata:
  format: evoloop-macro
  step_count: 2
steps:
  - type: action
    event_type: navigate
  - type: action
    event_type: click
"""
        result = macro_from_yaml(yaml_content)
        assert len(result) == 2
    
    def test_invalid_yaml_raises_error(self):
        with pytest.raises(YAMLError):
            safe_yaml_loads("invalid: yaml: [")
    
    def test_missing_steps_field(self):
        with pytest.raises(YAMLError):
            macro_from_yaml("name: test")  # No steps field
    
    def test_unwrapped_steps(self):
        """Test parsing YAML that is just a list of steps."""
        yaml_content = """
- type: action
  event_type: navigate
- type: action
  event_type: click
"""
        result = macro_from_yaml(yaml_content)
        assert len(result) == 2


class TestYAMLValidation:
    """Test YAML validation."""
    
    def test_valid_macro(self):
        yaml_content = """
steps:
  - type: action
    event_type: navigate
"""
        valid, errors = validate_macro_yaml(yaml_content)
        assert valid is True
        assert len(errors) == 0
    
    def test_missing_type_field(self):
        yaml_content = """
steps:
  - event_type: navigate
"""
        valid, errors = validate_macro_yaml(yaml_content)
        assert valid is False
        assert any("type" in e for e in errors)
    
    def test_invalid_yaml_syntax(self):
        yaml_content = "invalid: yaml: ["
        valid, errors = validate_macro_yaml(yaml_content)
        assert valid is False
        assert len(errors) > 0
    
    def test_empty_steps(self):
        yaml_content = """
steps: []
"""
        valid, errors = validate_macro_yaml(yaml_content)
        assert valid is True
        assert len(errors) == 0


class TestYAMLGeneration:
    """Test YAML generation from macro."""
    
    def test_generate_yaml(self):
        steps = [
            {"type": "action", "event_type": "navigate", "source": "dom"},
            {"type": "click", "target_selector": ".btn"}
        ]
        yaml_str = macro_to_yaml(steps)
        assert "version: '1.0'" in yaml_str or 'version: "1.0"' in yaml_str
        assert "steps:" in yaml_str
        # Verify round-trip
        parsed = macro_from_yaml(yaml_str)
        assert len(parsed) == 2
    
    def test_generate_preserves_structure(self):
        """Test that complex nested structures are preserved."""
        steps = [
            {
                "type": "if",
                "condition": {"type": "element_exists", "target_selector": ".modal"},
                "then_steps": [
                    {"type": "action", "event_type": "click"}
                ]
            }
        ]
        yaml_str = macro_to_yaml(steps)
        parsed = macro_from_yaml(yaml_str)
        assert parsed[0]["type"] == "if"
        assert len(parsed[0]["then_steps"]) == 1


class TestSafeYAMLLoads:
    """Test safe YAML loading."""
    
    def test_load_simple_mapping(self):
        result = safe_yaml_loads("key: value")
        assert result == {"key": "value"}
    
    def test_load_list(self):
        result = safe_yaml_loads("- item1\n- item2")
        assert result == ["item1", "item2"]
    
    def test_load_nested(self):
        result = safe_yaml_loads("""
outer:
  inner:
    key: value
""")
        assert result["outer"]["inner"]["key"] == "value"


class TestSafeYAMLDumps:
    """Test safe YAML dumping."""
    
    def test_dump_simple_dict(self):
        result = safe_yaml_dumps({"key": "value"})
        assert "key: value" in result
    
    def test_dump_preserves_order(self):
        """Test that key order is preserved (sort_keys=False)."""
        data = {"z": 1, "a": 2, "m": 3}
        result = safe_yaml_dumps(data)
        # Check that z comes before a
        z_pos = result.find("z:")
        a_pos = result.find("a:")
        assert z_pos < a_pos
    
    def test_dump_unicode(self):
        """Test that unicode is preserved (allow_unicode=True)."""
        result = safe_yaml_dumps({"key": "中文"})
        assert "中文" in result
