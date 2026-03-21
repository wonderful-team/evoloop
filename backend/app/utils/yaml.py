"""
YAML Utilities for Macro Script Processing

Provides safe YAML parsing and conversion to/from JSON.
"""

import yaml
from typing import Any
from yaml.scanner import ScannerError
from yaml.parser import ParserError


class YAMLError(Exception):
    """Custom YAML error with context."""
    pass


def safe_yaml_loads(content: str) -> Any:
    """
    Safely parse YAML content.
    
    Args:
        content: YAML string
        
    Returns:
        Parsed Python object
        
    Raises:
        YAMLError: If parsing fails
    """
    try:
        return yaml.safe_load(content)
    except (ScannerError, ParserError) as e:
        raise YAMLError(f"YAML parse error at line {e.problem_mark.line}: {e.problem}")


def safe_yaml_dumps(obj: Any, indent: int = 2) -> str:
    """
    Safely serialize object to YAML.
    
    Args:
        obj: Object to serialize
        indent: Indentation level
        
    Returns:
        YAML string
    """
    return yaml.safe_dump(
        obj,
        indent=indent,
        allow_unicode=True,
        sort_keys=False,  # Preserve key order for readability
        default_flow_style=False
    )


def macro_to_yaml(macro_steps: list[dict]) -> str:
    """
    Convert macro steps to human-friendly YAML format.
    
    Args:
        macro_steps: List of macro step dicts
        
    Returns:
        Formatted YAML string
    """
    # Add metadata header
    data = {
        "version": "1.0",
        "metadata": {
            "format": "evoloop-macro",
            "step_count": len(macro_steps)
        },
        "steps": macro_steps
    }
    return safe_yaml_dumps(data)


def macro_from_yaml(yaml_content: str) -> list[dict]:
    """
    Parse YAML macro and extract steps.
    
    Args:
        yaml_content: YAML string
        
    Returns:
        List of macro step dicts
        
    Raises:
        YAMLError: If format is invalid
    """
    data = safe_yaml_loads(yaml_content)
    
    if not isinstance(data, dict):
        raise YAMLError("YAML root must be a mapping")
    
    # Support both wrapped and unwrapped formats
    steps = data.get("steps", data.get("macro_script", data))
    
    if not isinstance(steps, list):
        raise YAMLError("Macro steps must be a list")
    
    return steps


def validate_macro_yaml(yaml_content: str) -> tuple[bool, list[str]]:
    """
    Validate YAML macro format without full parsing.
    
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    try:
        data = safe_yaml_loads(yaml_content)
    except YAMLError as e:
        return False, [str(e)]
    
    if not isinstance(data, (dict, list)):
        return False, ["YAML root must be a mapping or list"]
    
    steps = data.get("steps", data) if isinstance(data, dict) else data
    
    if not isinstance(steps, list):
        return False, ["'steps' must be a list"]
    
    # Validate each step has required fields
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"Step {i+1}: must be a mapping")
            continue
            
        if "type" not in step:
            errors.append(f"Step {i+1}: missing required field 'type'")
    
    return len(errors) == 0, errors
