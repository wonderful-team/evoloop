from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.tools.mcp.client import mcp_client_manager
from app.models.schemas.mcp import McpServerCreate

router = APIRouter()


@router.get("/servers", response_model=list[Any])
async def list_mcp_servers():
    """
    List all registered MCP servers.
    """
    servers = await mcp_client_manager.list_servers()
    # Ensure the response matches what frontend expects.
    # frontend wants: name, command, status, tools_count, args (optional)
    # backend list_servers returns list of dicts.
    return servers


@router.post("/server", response_model=Any)
async def add_mcp_server(server: McpServerCreate):
    """
    Register and connect a new MCP server.
    """
    try:
        details = {
            "command": server.command,
            "args": server.args or [],
            "env": server.env or {},
        }
        result = await mcp_client_manager.add_server(server.name, details)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/server/{name}", response_model=Any)
async def delete_mcp_server(name: str):
    """
    Remove an MCP server.
    """
    try:
        result = await mcp_client_manager.remove_server(name)
        if not result:
            raise HTTPException(status_code=404, detail="Server not found")
        return {"status": "success", "message": f"Server {name} removed"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
