from pydantic import BaseModel, Field
from typing import Any

class LegacyDictMixin:
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

class DynamicBaseModel(BaseModel, LegacyDictMixin):
    model_config = {"extra": "allow"}

class AgentRuntimeConfig(DynamicBaseModel):
    role_name: str
    system_instructions: str
    tools: list[str] = Field(default_factory=list)

try:
    data = {'role_name': '', 'system_instructions': ''}
    config = AgentRuntimeConfig.model_validate(data)
    print("Validation successful")
    print(config.model_dump())
except Exception as e:
    print("Validation failed")
    print(e)
