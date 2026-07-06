"""HITL sub-router — human-in-the-loop requests."""
from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUserOptional
from app.api.responses import BaseAPIResponse
from app.core.hitl import (
    cancel_request,
    cleanup_old_requests,
    complete_request,
    get_all_pending_requests,
    get_pending_request,
    get_pending_requests_for_thread,
)
from app.core.learning.schemas import HumanInputRequestOut, RespondRequest

router = APIRouter()


@router.get("/human-requests", response_model=list[HumanInputRequestOut])
async def list_pending_requests(thread_id: str | None = None, current_user: CurrentUserOptional = None):
    """Get all pending human input requests, optionally filtered by thread_id."""
    if thread_id:
        requests = await get_pending_requests_for_thread(thread_id)
        return [
            HumanInputRequestOut(
                id=req.id,
                thread_id=req.thread_id,
                request_type=req.request_type,
                prompt=req.prompt,
                options=req.options,
                context=req.context,
                default_value=req.default_value,
                created_at=req.created_at.isoformat(),
                status=req.status,
            )
            for req in requests
        ]

    requests_raw = await get_all_pending_requests()
    return [HumanInputRequestOut(**req) for req in requests_raw]


@router.get("/human-requests/{request_id}", response_model=HumanInputRequestOut)
async def get_request(request_id: str, current_user: CurrentUserOptional = None):
    """Get a specific human input request by ID."""
    request = await get_pending_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    return HumanInputRequestOut(
        id=request.id,
        thread_id=request.thread_id,
        request_type=request.request_type,
        prompt=request.prompt,
        options=request.options,
        context=request.context,
        default_value=request.default_value,
        created_at=request.created_at.isoformat(),
        status=request.status,
    )


@router.post("/human-requests/{request_id}/respond", response_model=BaseAPIResponse)
async def respond_to_request(request_id: str, body: RespondRequest, current_user: CurrentUserOptional = None):
    """Submit a response to a pending human input request."""
    request = await get_pending_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.status != "pending":
        raise HTTPException(
            status_code=400, detail=f"Request is not pending (status: {request.status})"
        )

    success = await complete_request(request_id, body.response)

    if success:
        return BaseAPIResponse(
            success=True, message=f"Response recorded for request {request_id}"
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to complete request")


@router.post("/human-requests/{request_id}/cancel", response_model=BaseAPIResponse)
async def cancel_pending_request(request_id: str, current_user: CurrentUserOptional = None):
    """Cancel a pending human input request."""
    request = await get_pending_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.status != "pending":
        raise HTTPException(
            status_code=400, detail=f"Request is not pending (status: {request.status})"
        )

    success = await cancel_request(request_id)

    if success:
        return BaseAPIResponse(success=True, message=f"Request {request_id} cancelled")
    else:
        raise HTTPException(status_code=500, detail="Failed to cancel request")


@router.post("/cleanup", response_model=BaseAPIResponse)
async def cleanup_requests(max_age_hours: int = 24, current_user: CurrentUserOptional = None):
    """Clean up old completed/cancelled requests."""
    await cleanup_old_requests(max_age_hours)
    return BaseAPIResponse(success=True, message="Cleanup completed")
