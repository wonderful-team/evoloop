from pydantic import BaseModel


class McpServerBase(BaseModel):
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

class McpServerUpdate(BaseModel):
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
