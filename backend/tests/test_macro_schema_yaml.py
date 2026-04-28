"""Tests for MacroScript YAML support in schema."""

import pytest
from app.core.execution.macro.schemas import MacroScript, MacroStep
from app.utils.yaml import YAMLError


class TestMacroScriptYAML:
    """Test MacroScript YAML parsing and generation."""
    
    def test_from_yaml_basic(self):
        yaml_content = """
version: "1.0"
metadata:
  format: evoloop-macro
steps:
  - type: action
    event_type: navigate
    source: dom
    description: Navigate to example
    payload:
      url: "https://example.com"
"""
        script = MacroScript.from_yaml(yaml_content)
        assert len(script.steps) == 1
        assert script.steps[0].type == "action"
        assert script.steps[0].event_type == "navigate"
    
    def test_from_yaml_with_loop(self):
        yaml_content = """
steps:
  - type: loop
    description: Process items
    max_iterations: 10
    steps:
      - type: action
        event_type: click
"""
        script = MacroScript.from_yaml(yaml_content)
        assert len(script.steps) == 1
        assert script.steps[0].type == "loop"
        assert len(script.steps[0].steps) == 1
    
    def test_to_yaml(self):
        steps = [
            MacroStep(type="action", event_type="navigate", source="dom"),
            MacroStep(type="action", event_type="click", source="dom", target_selector=".btn")
        ]
        script = MacroScript(steps=steps)
        yaml_str = script.to_yaml()
        
        # Verify it contains expected content
        assert "steps:" in yaml_str
        assert "type: action" in yaml_str
        
        # Verify round-trip
        parsed = MacroScript.from_yaml(yaml_str)
        assert len(parsed.steps) == 2
    
    def test_parse_auto_detect_yaml(self):
        """Test auto-detection of YAML format."""
        yaml_content = """
steps:
  - type: action
    event_type: navigate
"""
        script = MacroScript.parse(yaml_content, format="auto")
        assert len(script.steps) == 1
    
    def test_parse_auto_detect_json(self):
        """Test auto-detection of JSON format."""
        json_content = '[{"type": "action", "event_type": "navigate"}]'
        script = MacroScript.parse(json_content, format="auto")
        assert len(script.steps) == 1
    
    def test_parse_explicit_yaml(self):
        """Test explicit YAML format."""
        yaml_content = """
steps:
  - type: action
"""
        script = MacroScript.parse(yaml_content, format="yaml")
        assert len(script.steps) == 1
    
    def test_parse_explicit_json(self):
        """Test explicit JSON format."""
        json_content = '{"steps": [{"type": "action"}]}'
        script = MacroScript.parse(json_content, format="json")
        assert len(script.steps) == 1
    
    def test_parse_invalid_yaml(self):
        """Test that invalid YAML raises appropriate error."""
        with pytest.raises((YAMLError, ValueError)):
            MacroScript.parse("invalid: yaml: [", format="yaml")
    
    def test_parse_invalid_json(self):
        """Test that invalid JSON raises appropriate error."""
        with pytest.raises(ValueError):
            MacroScript.parse("not valid json", format="json")


class TestMacroStepYAMLCompatibility:
    """Test that MacroStep handles YAML-parsed data correctly."""
    
    def test_step_with_nested_payload(self):
        """Test steps with complex nested payloads from YAML."""
        yaml_content = """
steps:
  - type: action
    event_type: navigate
    payload:
      url: "https://example.com"
      headers:
        Authorization: "Bearer token"
        Content-Type: "application/json"
"""
        script = MacroScript.from_yaml(yaml_content)
        step = script.steps[0]
        assert step.payload["url"] == "https://example.com"
        assert step.payload["headers"]["Authorization"] == "Bearer token"
    
    def test_step_with_multiline_description(self):
        """Test steps with multiline descriptions from YAML."""
        yaml_content = """
steps:
  - type: action
    event_type: click
    description: |
      This is a multi-line description
      that spans multiple lines
      for better readability
"""
        script = MacroScript.from_yaml(yaml_content)
        step = script.steps[0]
        assert "multi-line description" in step.description
