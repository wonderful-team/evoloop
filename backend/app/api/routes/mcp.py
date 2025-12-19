from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from app.infrastructure.mcp.client import mcp_client_manager

router = APIRouter()

class McpServerRequest(BaseModel):
    name: str
    command: str
    args: List[str] = []
    env: Dict[str, str] = {}

@router.post("/server")
async def add_mcp_server(req: McpServerRequest):
    """Register a new MCP server."""
    details = {
        "command": req.command,
        "args": req.args,
        "env": req.env
    }
    try:
        res = await mcp_client_manager.add_server(req.name, details)
        return res
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@router.get("/servers")
async def list_mcp_servers():
    """List registered MCP servers."""
    return await mcp_client_manager.list_servers()

@router.delete("/server/{name}")
async def delete_mcp_server(name: str):
    """Remove an MCP server."""
    try:
        # Note: Need to implement remove_server in McpClientManager if it doesn't exist
        await mcp_client_manager.remove_server(name) 
        return {"status": "removed", "name": name}
    except Exception as e:
        raise HTTPException(500, str(e))
