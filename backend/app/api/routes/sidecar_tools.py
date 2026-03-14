"""
Sidecar Tool API - Endpoints for Tauri to execute tools on behalf of Server.

This module provides:
1. GET /pending_tools - Tauri polls for pending tool requests
2. POST /tool_result - Tauri submits tool execution results
3. GET /chat/{thread_id}/state - Get conversation state
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser, verify_guest_access
from app.core.tools.sidecar_proxy import tool_request_manager

router = APIRouter()


class ToolResultRequest(BaseModel):
    """Request to submit a tool execution result."""
    request_id: str
    result: Any | None = None
    error: str | None = None


class ToolRequestResponse(BaseModel):
    """Response containing tool request details."""
    request_id: str
    thread_id: str
    tool: str
    params: dict[str, Any]


@router.get("/pending_tools", dependencies=[Depends(verify_guest_access)])
async def get_pending_tools(
    thread_id: str | None = None,
    _current_user: CurrentUser = None,
) -> list[ToolRequestResponse]:
    """
    Get pending tool requests.

    Tauri polls this endpoint to get tools that need to be executed via Client.

    Args:
        thread_id: Optional filter by thread

    Returns:
        List of pending tool requests
    """
    if thread_id:
        requests = await tool_request_manager.get_pending_for_thread(thread_id)
    else:
        requests = await tool_request_manager.get_all_pending()

    return [
        ToolRequestResponse(
            request_id=req.request_id,
            thread_id=req.thread_id,
            tool=req.tool,
            params=req.params,
        )
        for req in requests
    ]


@router.post("/tool_result", dependencies=[Depends(verify_guest_access)])
async def submit_tool_result(
    req: ToolResultRequest,
    _current_user: CurrentUser = None,
) -> dict[str, bool]:
    """
    Submit a tool execution result.

    Tauri calls this after Client has executed the tool.

    Args:
        req: Tool result containing request_id and result/error

    Returns:
        Success status
    """
    success = await tool_request_manager.complete_request(
        request_id=req.request_id,
        result=req.result,
        error=req.error,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Request not found")

    return {"success": True}


@router.post("/chat/{thread_id}/tool_result", dependencies=[Depends(verify_guest_access)])
async def submit_thread_tool_result(
    thread_id: str,
    req: ToolResultRequest,
    _current_user: CurrentUser = None,
) -> dict[str, bool]:
    """
    Submit a tool result for a specific thread.

    Alternative endpoint that includes thread_id in URL for clarity.
    """
    return await submit_tool_result(req, _current_user)


@router.get("/chat/{thread_id}/state", dependencies=[Depends(verify_guest_access)])
async def get_thread_state(
    thread_id: str,
    _current_user: CurrentUser = None,
) -> dict[str, Any]:
    """
    Get the current state of a conversation thread.

    Returns:
        State including any pending tool requests
    """
    pending = await tool_request_manager.get_pending_for_thread(thread_id)

    return {
        "thread_id": thread_id,
        "pending_tools": [
            {
                "request_id": req.request_id,
                "tool": req.tool,
                "params": req.params,
                "created_at": req.created_at.isoformat(),
            }
            for req in pending
        ],
        "has_pending_tools": len(pending) > 0,
    }


@router.post("/chat/{thread_id}/cancel_tools", dependencies=[Depends(verify_guest_access)])
async def cancel_thread_tools(
    thread_id: str,
    _current_user: CurrentUser = None,
) -> dict[str, bool]:
    """
    Cancel all pending tool requests for a thread.

    Called when user stops the conversation or an error occurs.
    """
    await tool_request_manager.cancel_thread_requests(thread_id)
    return {"success": True}


# Webhook-style endpoint for Tauri to receive notifications
@router.post("/webhook/tool_request", dependencies=[Depends(verify_guest_access)])
async def webhook_tool_request(
    request_data: dict[str, Any],
    _current_user: CurrentUser = None,
) -> dict[str, str]:
    """
    Webhook endpoint for Tauri to acknowledge tool requests.

    This is optional - Tauri can also poll /pending_tools.
    Called by Server when a new tool request is created.
    """
    # Just acknowledge receipt - Tauri will poll for actual execution
    return {"status": "acknowledged"}
