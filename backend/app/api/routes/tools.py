from typing import Any

from fastapi import APIRouter

from app.domain.tools.registry import get_all_tools
from app.domain.tools.runtime_registry import get_runtime_tools

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/runtime")
async def list_runtime_tools() -> list[dict[str, Any]]:
    """
    List all dynamically created runtime tools.
    """
    tools = get_runtime_tools()
    results = []
    for t in tools:
        # Pydantic schema for args
        args_schema = t.args_schema.schema() if t.args_schema else {}
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
        args_schema = t.args_schema.schema() if t.args_schema else {}
        results.append({
            "name": t.name,
            "description": t.description,
            "args_schema": args_schema,
            "is_runtime": t.name in [rt.name for rt in get_runtime_tools()],
        })
    return results
