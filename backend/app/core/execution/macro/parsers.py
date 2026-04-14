"""
LLM Response Parsers for different formats

Supports parsing YAML and JSON macro outputs from LLM responses.
"""

import json
import re
from typing import Any

from app.utils.yaml import YAMLError, safe_yaml_loads


def extract_yaml_from_response(response: str) -> str | None:
    """
    Extract YAML content from LLM response.
    
    Looks for:
    1. Fenced code blocks with yaml/yml language tag
    2. Fenced code blocks without language tag (YAML-like content)
    3. Raw YAML starting with 'steps:' or '- '
    """
    # Try fenced code block with yaml tag
    patterns = [
        r'```yaml\n(.*?)\n```',
        r'```yml\n(.*?)\n```',
    ]

    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Try generic code block
    generic_match = re.search(r'```\n(.*?)\n```', response, re.DOTALL)
    if generic_match:
        content = generic_match.group(1).strip()
        # Check if it looks like YAML
        if content.startswith(('steps:', '- ', 'version:', 'metadata:')):
            return content

    # Try to find YAML-like structure at the start
    lines = response.strip().split('\n')
    if lines and lines[0].startswith(('steps:', '- ', 'version:', 'metadata:')):
        return response.strip()

    return None


def extract_json_from_response(response: str) -> str | None:
    """Extract JSON array or object from response."""
    # Try fenced code block
    patterns = [
        r'```json\n(.*?)\n```',
        r'```\n(.*?)\n```',
    ]

    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()

    # Try to find JSON array
    array_match = re.search(r'\[.*\]', response, re.DOTALL)
    if array_match:
        return array_match.group()

    # Try to find JSON object
    object_match = re.search(r'\{.*\}', response, re.DOTALL)
    if object_match:
        return object_match.group()

    return None


def parse_macro_response(response: str) -> list[dict]:
    """
    Parse LLM response containing macro steps.
    
    Supports:
    - YAML format (preferred, checked first)
    - JSON format (fallback for backward compatibility)
    
    Returns:
        List of macro step dicts
        
    Raises:
        ValueError: If neither YAML nor JSON can be parsed
    """
    errors = []

    # Try YAML first (preferred format)
    yaml_content = extract_yaml_from_response(response)
    if yaml_content:
        try:
            data = safe_yaml_loads(yaml_content)

            # Handle different YAML structures
            if isinstance(data, dict):
                steps = data.get("steps", data.get("macro_script"))
                if isinstance(steps, list):
                    return steps
            elif isinstance(data, list):
                return data

        except YAMLError as e:
            errors.append(f"YAML parse error: {e}")

    # Fallback to JSON (legacy format)
    json_content = extract_json_from_response(response)
    if json_content:
        try:
            data = json.loads(json_content)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                steps = data.get("steps", data.get("macro_script"))
                if isinstance(steps, list):
                    return steps
        except json.JSONDecodeError as e:
            errors.append(f"JSON parse error: {e}")

    # If we get here, both formats failed
    error_msg = "; ".join(errors) if errors else "Could not extract valid YAML or JSON macro"
    raise ValueError(f"Failed to parse macro response: {error_msg}")


def parse_analysis_response(response: str) -> dict[str, Any]:
    """
    Parse LLM analysis response (usually JSON format).
    
    Used for:
    - Redundancy check results
    - Verification results
    - Analysis results
    """
    # Try to extract JSON
    json_content = extract_json_from_response(response)
    if json_content:
        try:
            return json.loads(json_content)
        except json.JSONDecodeError:
            pass

    # Try YAML as fallback
    yaml_content = extract_yaml_from_response(response)
    if yaml_content:
        try:
            return safe_yaml_loads(yaml_content)
        except YAMLError:
            pass

    raise ValueError("Could not parse analysis response")
