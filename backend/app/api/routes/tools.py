from typing import Any

from fastapi import APIRouter

from app.core.tools.registry import get_all_tools
from app.core.tools.runtime_registry import get_runtime_tools

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/runtime")
async def list_runtime_tools() -> list[dict[str, Any]]:
    """
    List all dynamically created runtime tools.
    """
    tools = get_runtime_tools()
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
            {"name": t.name, "description": t.description, "args_schema": args_schema}
        )
    return results


@router.get("")
async def list_all_tools() -> list[dict[str, Any]]:
    """
    List ALL available tools (Static + Runtime).
    """
    tools = get_all_tools()
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

        results.append({
            "name": t.name,
            "description": t.description,
            "args_schema": args_schema,
            "is_runtime": t.name in [rt.name for rt in get_runtime_tools()],
        })
    return results
