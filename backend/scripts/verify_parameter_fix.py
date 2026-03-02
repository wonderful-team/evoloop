from pydantic import BaseModel
from typing import Any, List, Optional
import json

# Mock schemas from learning.py (simplified)
class SkillParameter(BaseModel):
    name: str
    type: str
    description: str
    default: Any = None
    required: bool = False

def _normalize_skill_params(params_raw: Any) -> List[dict]:
    if not params_raw:
        return []
    try:
        if isinstance(params_raw, str):
            data = json.loads(params_raw)
        else:
            data = params_raw
    except (json.JSONDecodeError, TypeError):
        return []
    normalized = []
    if isinstance(data, dict):
        for name, info in data.items():
            if isinstance(info, dict):
                normalized.append({
                    "name": name,
                    "type": info.get("type", "string"),
                    "description": info.get("description", ""),
                    "required": info.get("required", True),
                    "default": info.get("default")
                })
            else:
                normalized.append({
                    "name": name,
                    "type": "string",
                    "description": str(info),
                    "required": True,
                    "default": None
                })
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "name" in item:
                normalized.append({
                    "name": item["name"],
                    "type": item.get("type") or "string",
                    "description": item.get("description", ""),
                    "required": item.get("required", True),
                    "default": item.get("default")
                })
    return normalized

# Test cases
test_cases = [
    # Case 1: Legacy Dict
    {
        "input": {"target": {"type": "string", "description": "The application..."}},
        "expected_count": 1,
        "check": lambda res: res[0]["name"] == "target" and res[0]["type"] == "string"
    },
    # Case 2: Incomplete List (missing type)
    {
        "input": [{"name": "action", "description": "some action", "required": True}],
        "expected_count": 1,
        "check": lambda res: res[0]["name"] == "action" and res[0]["type"] == "string"
    },
    # Case 3: Standard List
    {
        "input": [{"name": "app_name", "type": "string", "description": "...", "required": True}],
        "expected_count": 1,
        "check": lambda res: res[0]["name"] == "app_name" and res[0]["type"] == "string"
    },
    # Case 4: Empty string
    {
        "input": "",
        "expected_count": 0,
        "check": lambda res: res == []
    }
]

def run_tests():
    for i, tc in enumerate(test_cases):
        print(f"Running test case {i+1}...")
        result = _normalize_skill_params(tc["input"])
        assert len(result) == tc["expected_count"], f"Expected {tc['expected_count']}, got {len(result)}"
        assert tc["check"](result), f"Check failed for result: {result}"
        
        # Pydantic validation check
        for p in result:
            SkillParameter(**p)
        print(f"Test case {i+1} PASSED")

if __name__ == "__main__":
    run_tests()
    print("\nAll normalization tests PASSED!")
