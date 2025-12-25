from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class McpServerBase(BaseModel):
    name: str
    command: str
    args: Optional[List[str]] = []
    env: Optional[Dict[str, str]] = {}

class McpServerCreate(McpServerBase):
    pass

class McpServerRead(McpServerBase):
    id: int
    status: str
    tools_count: int

class McpServerUpdate(BaseModel):
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
