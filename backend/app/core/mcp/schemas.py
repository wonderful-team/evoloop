from app.infrastructure.pydantic_base import DynamicBaseModel


class McpServerBase(DynamicBaseModel):
    name: str
    command: str
    args: list[str] | None = []
    env: dict[str, str] | None = {}


class McpServerCreate(McpServerBase):
    pass


class McpServerRead(McpServerBase):
    id: int
    status: str
    tools_count: int


class McpServerUpdate(DynamicBaseModel):
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
