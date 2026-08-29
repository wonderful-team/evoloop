"""Recording sub-router — trace recording sessions."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUserOptional, require_benefit
from app.core.learning.schemas import (
    RecordingSessionsResponse,
    StartRecordingRequest,
    StartRecordingResponse,
    StopRecordingResponse,
)
from app.utils.id import gen_uuid

from .shared import _active_sessions

router = APIRouter()


@router.post("/traces/start", response_model=StartRecordingResponse, dependencies=[Depends(require_benefit("skill_learning"))])
async def start_recording(body: StartRecordingRequest):
    """Start a new recording session for imitation learning."""
    session_id = gen_uuid()
    _active_sessions[session_id] = {
        "thread_id": body.thread_id,
        "task_name": body.task_name,
        "started_at": datetime.utcnow(),
    }

    return StartRecordingResponse(
        session_id=session_id,
        message=f"Recording session started for thread {body.thread_id}",
    )


async def _count_persisted_events(session_ids: list[str]) -> dict[str, int]:
    """Real persisted event counts per recording session (TraceEvent rows)."""
    if not session_ids:
        return {}
    from app.core.learning.trace.repository import trace_repository

    return await trace_repository.count_by_sessions(session_ids)


@router.post("/traces/stop", response_model=StopRecordingResponse)
async def stop_recording(session_id: str, current_user: CurrentUserOptional = None):
    """Stop a recording session."""
    if session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail="Recording session not found")

    _active_sessions.pop(session_id)
    counts = await _count_persisted_events([session_id])

    return StopRecordingResponse(
        session_id=session_id,
        event_count=counts.get(session_id, 0),
        message="Recording session stopped",
    )


@router.get("/traces/sessions", response_model=RecordingSessionsResponse)
async def list_recording_sessions(thread_id: str | None = None, current_user: CurrentUserOptional = None):
    """List active recording sessions."""
    counts = await _count_persisted_events(list(_active_sessions))
    sessions = []
    for sid, info in _active_sessions.items():
        if thread_id is None or info["thread_id"] == thread_id:
            sessions.append({
                "session_id": sid,
                "thread_id": info["thread_id"],
                "task_name": info.get("task_name"),
                "started_at": info["started_at"].isoformat(),
                "event_count": counts.get(sid, 0),
            })
    return RecordingSessionsResponse(sessions=sessions)
