"""
Learning API Routes.
Handles human-in-the-loop requests and imitation learning endpoints.
"""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.engine.tasks import run_agent_background
from app.domain.tools.human_input import (
    cancel_request,
    cleanup_old_requests,
    complete_request,
    get_all_pending_requests,
    get_pending_request,
    get_pending_requests_for_thread,
)
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import Conversation, Message

logger = logging.getLogger("evoloop.learning")

router = APIRouter()


# ============ Schemas ============

class HumanInputRequestOut(BaseModel):
    id: str
    thread_id: str
    request_type: str
    prompt: str
    options: list[str] | None = None
    context: str | None = None
    default_value: str | None = None
    created_at: str
    status: str


class ExecuteSkillRequest(BaseModel):
    thread_id: str
    params: dict[str, Any]
    project_id: int | None = 1


class RespondRequest(BaseModel):
    response: Any


class RespondResponse(BaseModel):
    success: bool
    message: str


# ============ Endpoints ============

@router.get("/human-requests", response_model=list[HumanInputRequestOut])
def list_pending_requests(thread_id: str | None = None):
    """
    Get all pending human input requests.
    Optionally filter by thread_id.
    """
    if thread_id:
        requests = get_pending_requests_for_thread(thread_id)
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
                status=req.status
            )
            for req in requests
        ]

    return get_all_pending_requests()


@router.get("/human-requests/{request_id}", response_model=HumanInputRequestOut)
def get_request(request_id: str):
    """
    Get a specific human input request by ID.
    """
    request = get_pending_request(request_id)
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
        status=request.status
    )


@router.post("/human-requests/{request_id}/respond", response_model=RespondResponse)
def respond_to_request(request_id: str, body: RespondRequest):
    """
    Submit a response to a pending human input request.
    This will resume the paused agent workflow.
    """
    request = get_pending_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Request is not pending (status: {request.status})"
        )

    success = complete_request(request_id, body.response)

    if success:
        return RespondResponse(
            success=True,
            message=f"Response recorded for request {request_id}"
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to complete request")


@router.post("/human-requests/{request_id}/cancel", response_model=RespondResponse)
def cancel_pending_request(request_id: str):
    """
    Cancel a pending human input request.
    The agent will receive the default value if set.
    """
    request = get_pending_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Request is not pending (status: {request.status})"
        )

    success = cancel_request(request_id)

    if success:
        return RespondResponse(
            success=True,
            message=f"Request {request_id} cancelled"
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to cancel request")


@router.post("/cleanup", response_model=RespondResponse)
def cleanup_requests(max_age_hours: int = 24):
    """
    Clean up old completed/cancelled requests.
    """
    cleanup_old_requests(max_age_hours)
    return RespondResponse(success=True, message="Cleanup completed")


# ============ Trace Recording API (Phase 1) ============

import json
from datetime import datetime
from uuid import uuid4

from app.infrastructure.database.sql.models import TraceEvent


class RecordedEvent(BaseModel):
    """Single recorded event from frontend."""
    timestamp: float  # Unix timestamp in ms
    event_type: str  # "click", "input", "message", "tool_result", "screenshot"
    target_selector: str | None = None  # CSS selector of target element
    target_text: str | None = None  # Text content of target element
    payload: dict | None = None  # Additional event data
    screenshot_base64: str | None = None  # Base64 encoded screenshot (optional)


class StartRecordingRequest(BaseModel):
    thread_id: str
    task_name: str | None = None


class StartRecordingResponse(BaseModel):
    session_id: str
    message: str


class RecordEventsRequest(BaseModel):
    session_id: str
    thread_id: str
    events: list[RecordedEvent]


class StopRecordingResponse(BaseModel):
    session_id: str
    event_count: int
    message: str


# In-memory session tracking
_active_sessions: dict[str, dict] = {}


@router.post("/traces/start", response_model=StartRecordingResponse)
async def start_recording(body: StartRecordingRequest):
    """
    Start a new recording session for imitation learning.
    Returns a session_id to associate events with.
    """
    session_id = str(uuid4())
    _active_sessions[session_id] = {
        "thread_id": body.thread_id,
        "task_name": body.task_name,
        "started_at": datetime.utcnow(),
        "event_count": 0
    }

    return StartRecordingResponse(
        session_id=session_id,
        message=f"Recording session started for thread {body.thread_id}"
    )


@router.post("/traces/events", response_model=RespondResponse)
async def record_events(body: RecordEventsRequest):
    """
    Record a batch of UI events from the frontend ActionRecorder.
    These are stored as TraceEvent rows with is_human_action=True.
    """
    if body.session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail="Recording session not found")

    session = _active_sessions[body.session_id]
    events_saved = 0

    try:
        async with session_scope() as db:
            for idx, event in enumerate(body.events):
                # Build UI element info
                ui_info = None
                if event.target_selector or event.target_text:
                    ui_info = json.dumps({
                        "selector": event.target_selector,
                        "text": event.target_text
                    })

                # Handle screenshot if provided
                screenshot_path = None
                if event.screenshot_base64:
                    try:
                        import base64
                        import os

                        # Ensure upload directory exists
                        upload_dir = settings.SCREENSHOTS_DIR
                        os.makedirs(upload_dir, exist_ok=True)

                        # Generate unique filename
                        filename = f"{body.session_id}_{idx}_{int(event.timestamp)}.png"
                        file_path = os.path.join(upload_dir, filename)

                        # Decode and save
                        # Remove header if present (e.g. "data:image/png;base64,")
                        b64_data = event.screenshot_base64
                        if "," in b64_data:
                            b64_data = b64_data.split(",", 1)[1]

                        with open(file_path, "wb") as f:
                            f.write(base64.b64decode(b64_data))

                        # Store relative path
                        screenshot_path = os.path.relpath(file_path, os.getcwd())
                    except Exception as e:
                        logger.warning(f"Failed to save screenshot: {e}")
                        # Don't fail the event recording, just skip screenshot
                        pass

                trace_event = TraceEvent(
                    thread_id=body.thread_id,
                    step_number=session["event_count"] + idx + 1,
                    node_name="user_interaction",
                    state_snapshot=json.dumps({"context": "user_recording"}),
                    action_type=event.event_type,
                    action_payload=json.dumps(event.payload or {}),
                    is_human_action=True,
                    screenshot_path=screenshot_path,
                    ui_element_info=ui_info,
                    recording_session_id=body.session_id,

                    # New columns population
                    session_id=body.session_id,
                    timestamp=event.timestamp,
                    event_type=event.event_type,
                    target_selector=event.target_selector,
                    target_text=event.target_text,
                    payload=event.payload
                )
                db.add(trace_event)
                events_saved += 1

            session["event_count"] += events_saved

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save events: {e}")

    return RespondResponse(success=True, message=f"Recorded {events_saved} events")


@router.post("/traces/stop", response_model=StopRecordingResponse)
async def stop_recording(session_id: str):
    """
    Stop a recording session.
    """
    if session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail="Recording session not found")

    session = _active_sessions.pop(session_id)

    return StopRecordingResponse(
        session_id=session_id,
        event_count=session["event_count"],
        message="Recording session stopped"
    )


@router.get("/traces/sessions")
async def list_recording_sessions(thread_id: str | None = None):
    """
    List active recording sessions.
    """
    sessions = []
    for sid, info in _active_sessions.items():
        if thread_id is None or info["thread_id"] == thread_id:
            sessions.append({
                "session_id": sid,
                "thread_id": info["thread_id"],
                "task_name": info.get("task_name"),
                "started_at": info["started_at"].isoformat(),
                "event_count": info["event_count"]
            })
    return {"sessions": sessions}


# ============ Skill Management API (Phase 2) ============

from app.core.learning.skill_synthesizer import EnhancedWorkflowSynthesizer
from app.infrastructure.database.sql.models import LearnedSkill


class SynthesizeRequest(BaseModel):
    thread_id: str
    session_id: str | None = None


class SkillResponse(BaseModel):
    id: int
    name: str
    description: str
    trigger_patterns: list[str]
    tools_used: list[str]
    success_count: int
    failure_count: int
    is_active: bool


@router.post("/skills/synthesize")
async def synthesize_skill(body: SynthesizeRequest):
    """
    Synthesize a new skill from a trace sequence.
    Uses LLM to analyze the trace and generate a reusable skill.
    """
    try:
        synthesizer = EnhancedWorkflowSynthesizer(body.thread_id, body.session_id)
        skill = await synthesizer.synthesize()

        # Persist to database
        async with session_scope() as db:
            db_skill = LearnedSkill(
                name=skill.name,
                description=skill.description,
                trigger_patterns=json.dumps(skill.trigger_patterns),
                parameters=json.dumps([p.__dict__ for p in skill.parameters]),
                preconditions=json.dumps(skill.preconditions),
                steps=json.dumps([s.__dict__ for s in skill.steps]),
                tools_used=json.dumps(skill.tools_used),
                source_thread_id=skill.source_thread_id,
                source_session_id=skill.source_session_id
            )
            db.add(db_skill)
            await db.flush()  # Get ID

            return {
                "success": True,
                "skill_id": db_skill.id,
                "skill_name": skill.name,
                "skill_yaml": skill.to_yaml()
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")


@router.get("/skills")
async def list_skills(active_only: bool = True):
    """
    List all learned skills.
    """
    async with session_scope() as db:
        from sqlalchemy import select

        stmt = select(LearnedSkill)
        if active_only:
            stmt = stmt.where(LearnedSkill.is_active == True)
        stmt = stmt.order_by(LearnedSkill.created_at.desc())

        result = await db.execute(stmt)
        skills = result.scalars().all()

        return {
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "trigger_patterns": json.loads(s.trigger_patterns),
                    "parameters": json.loads(s.parameters) if s.parameters else [],
                    "tools_used": json.loads(s.tools_used) if s.tools_used else [],
                    "success_count": s.success_count,
                    "failure_count": s.failure_count,
                    "is_active": s.is_active
                }
                for s in skills
            ]
        }


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: int):
    """
    Get full details of a specific skill.
    """
    async with session_scope() as db:
        from sqlalchemy import select

        stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
        result = await db.execute(stmt)
        skill = result.scalar_one_or_none()

        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        return {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "trigger_patterns": json.loads(skill.trigger_patterns),
            "parameters": json.loads(skill.parameters),
            "preconditions": json.loads(skill.preconditions) if skill.preconditions else [],
            "steps": json.loads(skill.steps),
            "tools_used": json.loads(skill.tools_used) if skill.tools_used else [],
            "source_thread_id": skill.source_thread_id,
            "source_session_id": skill.source_session_id,
            "success_count": skill.success_count,
            "failure_count": skill.failure_count,
            "is_active": skill.is_active
        }


@router.delete("/skills/{skill_id}")
async def deactivate_skill(skill_id: int):
    """
    Deactivate (soft delete) a skill.
    """
    async with session_scope() as db:
        from sqlalchemy import update

        stmt = update(LearnedSkill).where(LearnedSkill.id == skill_id).values(is_active=False)
        await db.execute(stmt)

    return {"success": True, "message": f"Skill {skill_id} deactivated"}


class UpdateSkillRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger_patterns: list[str] | None = None
    parameters: list[dict[str, Any]] | None = None


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: int, body: UpdateSkillRequest):
    """
    Update a learned skill.
    """
    async with session_scope() as db:
        from sqlalchemy import select

        # 1. Get Skill
        stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
        result = await db.execute(stmt)
        skill = result.scalar_one_or_none()

        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        # 2. Update Fields
        if body.name:
            # Check uniqueness if name changed
            if body.name != skill.name:
                stmt_check = select(LearnedSkill).where(LearnedSkill.name == body.name)
                existing = (await db.execute(stmt_check)).scalar_one_or_none()
                if existing:
                     raise HTTPException(status_code=400, detail=f"Skill name '{body.name}' already exists")
            skill.name = body.name

        if body.description:
            skill.description = body.description

        if body.trigger_patterns is not None:
            skill.trigger_patterns = json.dumps(body.trigger_patterns)

        if body.parameters is not None:
             # Just dump the list of dicts directly
            skill.parameters = json.dumps(body.parameters)

        # 3. Commit (Automatic via session_scope exit, but we want to return updated data)
        await db.flush()

        return {
            "success": True,
            "message": f"Skill {skill_id} updated",
            "skill": {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "trigger_patterns": json.loads(skill.trigger_patterns),
                "parameters": json.loads(skill.parameters)
            }
        }


@router.post("/skills/{skill_id}/execute")
async def execute_skill(
    skill_id: int,
    body: ExecuteSkillRequest,
    bg_tasks: BackgroundTasks
):
    """
    Execute a skill by injecting a directive into the agent's conversation.
    This ensures the skill runs with full project context and history.
    """
    async with session_scope() as db:
        # 1. Verify Skill exists
        from app.infrastructure.database.sql.models import LearnedSkill
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        # 2. Construct Directive Message
        # We format this as a user message to "prompt" the agent to run the skill.
        skill_name = skill.name
        params_str = json.dumps(body.params, indent=2)
        directive = (
            f"Please execute the skill '{skill_name}' with the following parameters:\n"
            f"```json\n{params_str}\n```\n"
            f"Use the SkillExecutor to run this."
        )

        # 3. Persist Message to History
        # Ensure conversation exists
        conversation = await db.get(Conversation, body.thread_id)
        if not conversation:
            # Create if missing (though usually should exist for a thread)
             conversation = Conversation(
                id=body.thread_id,
                project_id=body.project_id,
                title=f"Execute {skill_name}",
            )
             db.add(conversation)

        # Add User Message
        user_msg = Message(
            thread_id=body.thread_id,
            project_id=body.project_id,
            role="human",
            content=directive,
            sequence_number=999999, # Temporary lazy sequence, effectively "next"
        )
        db.add(user_msg)
        await db.flush()

    # 4. Trigger Agent Loop
    inputs = {
        "messages": [{"type": "human", "content": directive}],
        "project_id": body.project_id
    }
    bg_tasks.add_task(run_agent_background, body.thread_id, inputs)

    return {"success": True, "message": f"Skill execution queued for '{skill_name}'"}
