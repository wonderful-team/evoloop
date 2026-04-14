from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional

class LegacyDictMixin:
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

class DynamicBaseModel(BaseModel, LegacyDictMixin):
    model_config = ConfigDict(extra="allow")

class AgentRuntimeConfig(DynamicBaseModel):
    role_name: str = ""
    system_instructions: str = ""
    tools: list[str] = Field(default_factory=list)
    model_override: Optional[str] = None

try:
    print("Attempt 1: Empty constructor")
    config = AgentRuntimeConfig()
    print(f"Success: {config.model_dump()}")
except Exception as e:
    print(f"Failure 1: {e}")

try:
    print("\nAttempt 2: Dict with some fields missing 'tools'")
    data = {'role_name': '', 'system_instructions': ''}
    config = AgentRuntimeConfig(**data)
    print(f"Success: {config.model_dump()}")
except Exception as e:
    print(f"Failure 2: {e}")

try:
    print("\nAttempt 3: model_validate with missing 'tools'")
    data = {'role_name': '', 'system_instructions': ''}
    config = AgentRuntimeConfig.model_validate(data)
    print(f"Success: {config.model_dump()}")
except Exception as e:
    print(f"Failure 3: {e}")

try:
    print("\nAttempt 4: tools=None")
    config = AgentRuntimeConfig(role_name="test", tools=None)
    print(f"Success: {config.model_dump()}")
except Exception as e:
    print(f"Failure 4: {e}")
