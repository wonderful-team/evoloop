from typing import Any

from fastapi import APIRouter

from app.core.tools.manager import tool_manager
from app.core.tools.registry import REGISTRY
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.api.schemas.tools import ToolInfo

router = APIRouter(prefix="/tools", tags=["tools"])

@router.get("/runtime")
async def list_runtime_tools() -> list[ToolInfo]:
    """
    List all dynamically created runtime tools.
    """
    tools = REGISTRY.get_runtime_tools()
    results = []
    for t in tools:
        # Pydantic schema for args - handle V2 and V1 safely
        args_schema = {}
        if t.args_schema:
            if hasattr(t.args_schema, "model_json_schema"):
                args_schema = t.args_schema.model_json_schema()
            elif hasattr(t.args_schema, "schema"):
                args_schema = t.args_schema.schema()
            else:
                args_schema = t.args_schema

        results.append(
            ToolInfo(name=t.name, description=t.description, args_schema=args_schema)
        )
    return results

@router.get("")
async def list_all_tools() -> list[ToolInfo]:
    """
    List ALL available tools (Static + Runtime).
    """
    tools = await tool_manager.get_all_capabilities()
    results = []
    for t in tools:
        args_schema = {}
        if t.args_schema:
            if hasattr(t.args_schema, "model_json_schema"):
                args_schema = t.args_schema.model_json_schema()
            elif hasattr(t.args_schema, "schema"):
                args_schema = t.args_schema.schema()
            else:
                args_schema = t.args_schema

        results.append(ToolInfo(
            name=t.name,
            description=t.description,
            args_schema=args_schema,
            is_runtime=t.name in [rt.name for rt in REGISTRY.get_runtime_tools()],
        ))
    return results