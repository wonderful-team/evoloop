"""
Learning API Routes.
Handles human-in-the-loop requests and imitation learning endpoints.
"""
import base64
import json
import logging
import math
import os
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_, func, select, update

from app.core.engine.background_agent import run_agent_background
from app.core.learning.skill_importer import SkillImporter
from app.core.learning.skill_synthesizer import WorkflowSynthesizer
from app.core.learning.skill_validator import SkillValidator
from app.core.learning.multimodal_synthesizer import (
    MultimodalSkillSynthesizer,
    RecordingSession,
)
from app.core.environment.controllers.mirror_session import mirror_manager
from app.domain.tools.human_input import (
    cancel_request,
    cleanup_old_requests,
    complete_request,
    get_all_pending_requests,
    get_pending_request,
    get_pending_requests_for_thread,
)
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.drivers.adb import adb_driver
from app.models import (
    Conversation,
    LearnedSkill,
    Message,
    RecordingAnnotation,
    SynthesisJob,
    TraceEvent,
)
from app.core.environment.capabilities.registry import ActionRegistry

logger = logging.getLogger(__name__)

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


class StartMirrorRequest(BaseModel):
    device_id: str


class StopMirrorRequest(BaseModel):
    session_id: str


class ImportSkillsRequest(BaseModel):
    directory: str


class SkillParameter(BaseModel):
    name: str
    type: str
    description: str
    default: Any | None = None
    required: bool = False


class SkillDTO(BaseModel):
    id: int
    name: str
    description: str
    namespace: str | None = None
    trigger_patterns: list[str]
    parameters: list[SkillParameter]
    tools_used: list[str]
    success_count: int
    failure_count: int
    is_active: bool
    status: str
    execution_mode: str = "agentic"
    macro_script: list[dict] | None = None
    validation_report: dict[str, Any] | None = None
    instructions: str | None = None
    created_at: datetime
    updated_at: datetime


class PaginatedSkillsResponse(BaseModel):
    items: list[SkillDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ Endpoints ============


@router.get("/capabilities/actions")
async def get_action_registry():
    """Export the centralized action registry for frontend sync."""
    return [a.dict() for a in ActionRegistry.list_actions()]


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
                status=req.status,
            )
            for req in requests
        ]

    return get_all_pending_requests()


def _normalize_skill_params(params_raw: str | list | dict | None) -> list[dict]:
    """
    Normalize skill parameters from various formats (dict, incomplete list)
    to a standard list of SkillParameter objects for the API.
    """
    if not params_raw:
        return []

    try:
        if isinstance(params_raw, str):
            data = json.loads(params_raw)
        else:
            data = params_raw
    except (json.JSONDecodeError, TypeError):
        return []

    normalized = []

    # Case 1: Legacy Dict format {"param_name": {"type": "...", "description": "..."}}
    if isinstance(data, dict):
        for name, info in data.items():
            if isinstance(info, dict):
                normalized.append({
                    "name": name,
                    "type": info.get("type", "string"),
                    "description": info.get("description", ""),
                    "required": info.get("required", True),
                    "default": info.get("default")
                })
            else:
                # Fallback for simple key-value if any
                normalized.append({
                    "name": name,
                    "type": "string",
                    "description": str(info),
                    "required": True,
                    "default": None
                })

    # Case 2: List format (ensure all required fields exist)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "name" in item:
                normalized.append({
                    "name": item["name"],
                    "type": item.get("type") or "string", # Fix for missing type
                    "description": item.get("description", ""),
                    "required": item.get("required", True),
                    "default": item.get("default")
                })

    return normalized


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
        status=request.status,
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
            status_code=400, detail=f"Request is not pending (status: {request.status})"
        )

    success = complete_request(request_id, body.response)

    if success:
        return RespondResponse(
            success=True, message=f"Response recorded for request {request_id}"
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
            status_code=400, detail=f"Request is not pending (status: {request.status})"
        )

    success = cancel_request(request_id)

    if success:
        return RespondResponse(success=True, message=f"Request {request_id} cancelled")
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


class GlobalRecordedEvent(BaseModel):
    timestamp: float
    event_type: str  # "key_press", "mouse_click", "window_change"
    key: str | None = None
    mouse_button: str | None = None
    position: tuple[float, float] | None = None
    window_title: str | None = None
    app_name: str | None = None
    process_id: int | None = None
    window_bounds: tuple[float, float, float, float] | None = None


class UploadScreenshotResponse(BaseModel):
    success: bool
    path: str
    message: str


class RecordGlobalEventsRequest(BaseModel):
    thread_id: str
    session_id: str | None = None
    events: list[GlobalRecordedEvent]


class ExtractKeyframesRequest(BaseModel):
    """Request to extract keyframes from a screen recording video."""
    session_id: str
    video_path: str
    thread_id: str | None = None


@router.post("/traces/global-events", response_model=RespondResponse)
async def record_global_events(body: RecordGlobalEventsRequest):
    """
    Record global observation events from Rust layer.
    """
    try:
        async with session_scope() as db:
            events_saved = 0
            for idx, event in enumerate(body.events):
                # Ensure we have a valid step number, maybe increment from last?
                # For simplicity in global recording, we just use idx if session tracking is loose
                # Or better, fetch last step number. But for high throughput, maybe just auto-increment via DB or loose idx
                # Using 0-indexed relative to batch for now

                trace_event = TraceEvent(
                    thread_id=body.thread_id,
                    step_number=idx, # Logic to be refined for continuity
                    node_name="global_observation",
                    action_type=event.event_type,
                    is_human_action=True,
                    source="global",
                    window_title=event.window_title,
                    app_name=event.app_name,
                    process_id=event.process_id,
                    mouse_x=event.position[0] if event.position else None,
                    mouse_y=event.position[1] if event.position else None,
                    key_name=event.key,
                    mouse_button=event.mouse_button,
                    state_snapshot=json.dumps({"context": "global_recording"}),
                    action_payload=json.dumps({"window_bounds": event.window_bounds}) if event.window_bounds else json.dumps({}),
                    recording_session_id=body.session_id,
                    # Compatibility fields
                    session_id=body.session_id,
                    timestamp=event.timestamp,
                    event_type=event.event_type,
                )
                db.add(trace_event)
                events_saved += 1

            return RespondResponse(success=True, message=f"Recorded {events_saved} global events")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save global events: {e}")


@router.post("/traces/extract-keyframes")
async def extract_keyframes(body: ExtractKeyframesRequest, background_tasks: BackgroundTasks):
    """
    Extract keyframes from a screen recording video at event timestamps.
    Called after recording stops. Runs extraction in the background.
    """
    from app.core.learning.frame_extractor import FrameExtractor

    async def _extract_and_update():
        try:
            # 1. Query all global events for this session to get timestamps
            async with session_scope() as db:
                stmt = (
                    select(TraceEvent)
                    .where(TraceEvent.recording_session_id == body.session_id)
                    # Support both global and dom sources
                    .where(TraceEvent.source.in_(["global", "dom", "cli"]))
                    # Handle different naming conventions: 'click', 'mouse_click', 'MouseButtonPress', etc.
                    .where(or_(
                        TraceEvent.event_type.ilike("%click%"),
                        TraceEvent.event_type.ilike("%press%"),
                        TraceEvent.event_type.in_(["input", "enter", "tab"])
                    ))
                    .order_by(TraceEvent.timestamp)
                )
                result = await db.execute(stmt)
                events = result.scalars().all()

            logger.info(f"Found {len(events)} events for session {body.session_id} to extract keyframes from")

            if not events:
                logger.warning(f"No matching events (click/press) found for session {body.session_id} in sources ['global', 'dom', 'cli']")
                return

            # 2. Extract timestamps (convert to ms)
            timestamps_ms = []
            event_ids = []
            base_ts = events[0].timestamp if events else 0
            for evt in events:
                if evt.timestamp:
                    relative_ms = int((evt.timestamp - base_ts) * 1000) if base_ts else int(evt.timestamp)
                    timestamps_ms.append(relative_ms)
                    event_ids.append(evt.id)

            # 3. Extract frames and analyze with OCR
            extractor = FrameExtractor(body.video_path, session_id=body.session_id)
            # Use extract_and_analyze instead of extract_frames
            results = await extractor.extract_and_analyze(timestamps_ms)

            # 4. Write screenshot paths and OCR data back to DB
            async with session_scope() as db:
                for event_id, result in zip(event_ids, results):
                    frame_path = result.get("screenshot_path")
                    ocr_elements = result.get("ocr_elements", [])

                    # Prepare update values
                    update_values = {"screenshot_path": frame_path}

                    # Geometry Matching: Find element at click position
                    # We need to fetch the event again or use cached data to get coordinates
                    # Since we are inside a new session scope/transaction context, let's fetch strictly needed info
                    # But we have event_id, so we can do a targeted update with logic?
                    # Actually, we need the event coordinates to match.
                    # Let's re-fetch the specific event to get its coordinates for matching.
                    stmt_evt = select(TraceEvent).where(TraceEvent.id == event_id)
                    evt = (await db.execute(stmt_evt)).scalar_one_or_none()

                    if evt and evt.mouse_x is not None and evt.mouse_y is not None:
                        # Find matching element
                        mx, my = evt.mouse_x, evt.mouse_y
                        matched_text = None

                        # Simple point-in-rect check
                        for el in ocr_elements:
                            # bounds: [x, y, w, h] (top-left, usually? Wait, frame_extractor said: [x-w/2, y-h/2, w, h])
                            # frame_extractor logic: bounds=[el.x - el.width//2, el.y - el.height//2, el.width, el.height]
                            # So it is [left, top, width, height]
                            x, y, w, h = el["bounds"]
                            if x <= mx <= x + w and y <= my <= y + h:
                                matched_text = el["text"]
                                break

                        if matched_text:
                            update_values["target_text"] = matched_text
                            # Also update ui_element_info for redundancy/compatibility
                            info = {}
                            if evt.ui_element_info:
                                try:
                                    info = json.loads(evt.ui_element_info)
                                except:
                                    pass
                            info["text"] = matched_text
                            info["source"] = "ocr_global"
                            update_values["ui_element_info"] = json.dumps(info)

                            logger.info(f"OCR Match for event {event_id}: '{matched_text}' at ({mx}, {my})")

                    # Perform the update
                    await db.execute(
                        update(TraceEvent)
                        .where(TraceEvent.id == event_id)
                        .values(**update_values)
                    )

            logger.info(
                f"Extracted and analyzed {len(results)} keyframes for session {body.session_id}"
            )

        except FileNotFoundError as e:
            logger.error(f"Keyframe extraction failed: {e}")
        except Exception as e:
            logger.exception(f"Keyframe extraction error: {e}")

    background_tasks.add_task(_extract_and_update)

    return {
        "success": True,
        "message": f"Keyframe extraction and OCR analysis started for session {body.session_id}",
    }


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
        "event_count": 0,
    }

    return StartRecordingResponse(
        session_id=session_id,
        message=f"Recording session started for thread {body.thread_id}",
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
                        # Use hierarchical storage for dataset (IL training data)
                        from app.core.vision.storage import screenshot_storage

                        # Decode base64
                        b64_data = event.screenshot_base64
                        if "," in b64_data:
                            b64_data = b64_data.split(",", 1)[1]

                        image_data = base64.b64decode(b64_data)

                        # Save to dataset directory with session organization
                        screenshot_path = screenshot_storage.save_screenshot(
                            image_data=image_data,
                            purpose="dataset",
                            platform="macos",  # Desktop recording
                            bundle_id=body.session_id,  # Use session_id for organization
                            suffix=f"event_{idx}"
                        )

                        logger.debug(f"Saved screenshot to: {screenshot_path}")
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
                    payload=event.payload,
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
        message="Recording session stopped",
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
                "event_count": info["event_count"],
            })
    return {"sessions": sessions}


# ============ Skill Management API (Phase 2) ============


class SynthesizeRequest(BaseModel):
    thread_id: str
    session_id: str | None = None
    auto_optimize: bool = True


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
        synthesizer = WorkflowSynthesizer(body.thread_id, body.session_id)
        skill = await synthesizer.synthesize(auto_optimize=body.auto_optimize)

        # Persist to database
        async with session_scope() as db:
            # Handle potential name collisions (psycopg.errors.UniqueViolation)
            base_name = skill.name
            unique_name = base_name
            counter = 1

            while True:
                # Check if name exists
                stmt = select(LearnedSkill).where(LearnedSkill.name == unique_name)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if not existing:
                    break
                # Conflict found, append suffix
                unique_name = f"{base_name}_{counter}"
                counter += 1

            if unique_name != base_name:
                logger.info(f"Skill name collision: {base_name} -> {unique_name}")

            db_skill = LearnedSkill(
                name=unique_name,
                description=skill.description,
                trigger_patterns=json.dumps(skill.trigger_patterns),
                parameters=json.dumps([p.__dict__ for p in skill.parameters]),
                preconditions=json.dumps(skill.preconditions),
                tools_used=json.dumps(skill.tools_used),
                source_thread_id=skill.source_thread_id,
                source_session_id=skill.source_session_id,
                is_active=True,
                instructions=skill.instructions,
                execution_mode=skill.execution_mode,
                macro_script=skill.macro_script,
            )
            db.add(db_skill)
            await db.flush()  # Get ID

            return {
                "success": True,
                "skill_id": db_skill.id,
                "skill_name": unique_name,
                "skill_yaml": skill.to_yaml(),
            }

    except Exception as e:
        logger.exception(f"Skill synthesis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")


@router.post("/skills/import")
async def import_skills(body: ImportSkillsRequest):
    """
    Bulk import skills from a local directory (containing SKILL.md folders).
    """
    try:
        results = await SkillImporter.import_from_directory(body.directory)
        return {
            "success": True,
            "results": results
        }
    except Exception as e:
        logger.exception(f"Skill import failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/skills", response_model=PaginatedSkillsResponse)
async def list_skills(
    active_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """
    List all learned skills with pagination.
    """
    async with session_scope() as db:
        # 1. Base Query
        stmt = select(LearnedSkill)
        if active_only:
            stmt = stmt.where(LearnedSkill.is_active == True)

        # 2. Get Total Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        # 3. Apply Pagination
        stmt = stmt.order_by(LearnedSkill.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        skills = result.scalars().all()

        total_pages = math.ceil(total / page_size) if page_size > 0 else 0

        return {
            "items": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "trigger_patterns": json.loads(s.trigger_patterns) if s.trigger_patterns else [],
                    "parameters": _normalize_skill_params(s.parameters),
                    "tools_used": json.loads(s.tools_used) if s.tools_used else [],
                    "success_count": s.success_count,
                    "failure_count": s.failure_count,
                    "is_active": s.is_active,
                    "status": s.status,
                    "execution_mode": s.execution_mode,
                    "macro_script": s.macro_script,
                    "validation_report": s.validation_report,
                    "instructions": s.instructions,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
                for s in skills
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: int):
    """
    Get full details of a specific skill.
    """
    async with session_scope() as db:
        stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
        result = await db.execute(stmt)
        skill = result.scalar_one_or_none()

        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        return {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "namespace": skill.namespace,
            "trigger_patterns": json.loads(skill.trigger_patterns) if skill.trigger_patterns else [],
            "parameters": _normalize_skill_params(skill.parameters),
            "preconditions": json.loads(skill.preconditions) if skill.preconditions else [],
            "tools_used": json.loads(skill.tools_used) if skill.tools_used else [],
            "source_thread_id": skill.source_thread_id,
            "source_session_id": skill.source_session_id,
            "success_count": skill.success_count,
            "failure_count": skill.failure_count,
            "is_active": skill.is_active,
            "status": skill.status,
            "execution_mode": skill.execution_mode,
            "macro_script": skill.macro_script,
            "validation_report": skill.validation_report,
            "instructions": skill.instructions,
            "resource_path": skill.resource_path,
        }


@router.delete("/skills/{skill_id}")
async def deactivate_skill(skill_id: int):
    """
    Deactivate (soft delete) a skill.
    """
    async with session_scope() as db:
        stmt = update(LearnedSkill).where(LearnedSkill.id == skill_id).values(is_active=False)
        await db.execute(stmt)

    return {"success": True, "message": f"Skill {skill_id} deactivated"}


class UpdateSkillRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    namespace: str | None = None
    trigger_patterns: list[str] | None = None
    parameters: list[dict[str, Any]] | None = None
    instructions: str | None = None
    preconditions: list[dict[str, Any]] | None = None
    execution_mode: str | None = None
    macro_script: list[dict] | None = None


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: int, body: UpdateSkillRequest):
    """
    Update a learned skill.
    """
    async with session_scope() as db:
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

        if body.namespace:
            skill.namespace = body.namespace

        if body.instructions is not None:
            skill.instructions = body.instructions

        if body.trigger_patterns is not None:
            skill.trigger_patterns = json.dumps(body.trigger_patterns)

        if body.parameters is not None:
            # Just dump the list of dicts directly
            skill.parameters = json.dumps(body.parameters)

        if body.preconditions is not None:
            skill.preconditions = json.dumps(body.preconditions)

        if body.execution_mode is not None:
            skill.execution_mode = body.execution_mode
            
        if body.macro_script is not None:
            skill.macro_script = body.macro_script

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
                "parameters": json.loads(skill.parameters),
            },
        }


async def execute_macro_with_fallback(thread_id: str, project_id: int, skill_id: int, skill_name: str, macro_payload: list, params: dict):
    from app.core.execution.macro.schema import MacroService
    result = await MacroService.run(thread_id, macro_payload, params)
    
    if result.get("status") == "fallback_required":
        logger.warning(f"[{thread_id}] Macro failed, triggering Agentic Fallback...")
        fallback_ctx = result.get("fallback_context", {})
        
        fallback_msg = (
            f"SYSTEM ALERT: The deterministic macro for '{skill_name}' failed.\n"
            f"As Supervisor, you must now ANALYZE the failure context and DELEGATE a fix to a specialized Worker.\n\n"
            f"Failure Context:\n{json.dumps(fallback_ctx, indent=2, ensure_ascii=False)}\n\n"
            f"Your Goal:\n"
            f"1. Check the failed step and reason.\n"
            f"2. Call `route_to('worker', ...)` with an appropriate role (e.g., 'Automation Specialist') to heal the process and complete the user's original request."
        )
        
        # Persist as 'human' to force Agent supervisor to treat it as a task
        async with session_scope() as db:
            msg = Message(
                thread_id=thread_id,
                project_id=project_id,
                role="human",
                content=fallback_msg,
                sequence_number=999999,
            )
            db.add(msg)
            await db.commit()
            
        inputs = {
            "messages": [{"type": "human", "content": fallback_msg}],
            "project_id": project_id,
            "metadata": {
                "original_skill_id": skill_id,
                "is_fallback_recovery": True
            }
        }
        
        # Hand over execution to the main Agent Loop
        await run_agent_background(thread_id, inputs)


@router.post("/skills/{skill_id}/execute")
async def execute_skill(
    skill_id: int, body: ExecuteSkillRequest, bg_tasks: BackgroundTasks
):
    """
    Execute a skill by injecting a directive into the agent's conversation.
    This ensures the skill runs with full project context and history.
    """
    async with session_scope() as db:
        # 1. Verify Skill exists
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        # 2. Construct Directive Message
        # We format this as a user message to prompt the agent to use the skill knowledge.
        # Since Worker Nodes (Operator, etc.) now retrieve skills based on this topic,
        # the agent will automatically see the 'Expert Guide' in its system prompt.
        skill_name = skill.name
        params_str = json.dumps(body.params, indent=2)
        directive = (
            f"User Instruction: I need you to perform the task '{skill_name}' using your expertise.\n"
            f"Parameters: {params_str}\n\n"
            f"Please refer to the 'EXPERT GUIDANCE (SKILLS)' section in your system instructions for the '{skill_name}' and use your tools to complete it."
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
            sequence_number=999999,  # Temporary lazy sequence, effectively "next"
        )
        db.add(user_msg)
        await db.commit()

    # 4. Trigger the desired execution mode
    if skill.execution_mode == "deterministic" and skill.macro_script:
        import copy
        
        # Deepcopy to avoid mutating the skill model in cache
        macro_payload = copy.deepcopy(skill.macro_script)
        bg_tasks.add_task(execute_macro_with_fallback, body.thread_id, body.project_id, skill.id, skill_name, macro_payload, body.params)
        return {"success": True, "message": f"Deterministic Macro execution queued for '{skill_name}'"}
    else:
        # Fallback to Agentic mode
        inputs = {
            "messages": [{"type": "human", "content": directive}],
            "project_id": body.project_id,
        }
        bg_tasks.add_task(run_agent_background, body.thread_id, inputs)
    
        return {"success": True, "message": f"Agentic execution queued for '{skill_name}'"}


# ============ Mirror Control API (Phase 4) ============


@router.get("/mirror/devices")
async def list_mirror_devices():
    """List connected Android devices for mirroring."""
    devices = adb_driver.list_devices()

    # Check for scrcpy availability
    scrcpy_available = False
    try:
        subprocess.run(["scrcpy", "--version"], capture_output=True, text=True)
        scrcpy_available = True
    except FileNotFoundError:
        pass

    return {
        "devices": devices,
        "scrcpy_available": scrcpy_available
    }


@router.post("/mirror/start")
async def start_mirror_session(body: StartMirrorRequest):
    """Start a scrcpy mirroring session."""
    session = await mirror_manager.create_session(body.device_id)
    if not session.is_active:
        raise HTTPException(status_code=500, detail=session.error or "Failed to start mirroring session")

    return {
        "success": True,
        "session_id": session.session_id,
        "device_id": session.device_id
    }


@router.post("/mirror/stop")
async def stop_mirror_session(body: StopMirrorRequest):
    """Stop an active mirroring session."""
    success = mirror_manager.stop_session(body.session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "message": "Mirroring session stopped"}


@router.post("/assets/upload-screenshot", response_model=UploadScreenshotResponse)
async def upload_screenshot(file: UploadFile = File(...)):
    """
    Upload a screenshot for a skill step.
    Uses hierarchical storage (dataset category for training data).
    """
    try:
        # Use hierarchical storage for dataset
        from app.core.vision.storage import screenshot_storage

        # Read file content
        content = await file.read()

        # Save to dataset directory
        file_path = screenshot_storage.save_screenshot(
            image_data=content,
            purpose="dataset",
            platform="macos",
            suffix=f"upload_{file.filename}"
        )

        return UploadScreenshotResponse(
            success=True,
            path=file_path,
            message="Screenshot uploaded successfully"
        )
    except Exception as e:
        logger.error(f"Failed to upload screenshot: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload screenshot: {str(e)}")


@router.get("/skills/{skill_id}/validate")
async def validate_skill(skill_id: int):
    """
    Run the validator on a skill and return its health status.
    """
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if not skill.resource_path:
            return {"success": False, "error": "Skill has no resource path (cannot validate)"}

        validation = SkillValidator.validate_folder(Path(skill.resource_path))

        # Update skill record with new validation report
        skill.validation_report = validation.dict()
        skill.status = "verified" if validation.status == "healthy" else "candidate"

        return {
            "success": True,
            "validation": validation.dict()
        }


# ============ Multimodal Synthesis API (NEW) ============


class SynthesizeFromRecordingRequest(BaseModel):
    """从录制合成 Skill 的请求"""
    video_path: str           # Tauri 返回的视频文件路径
    session_id: str           # 关联事件的 session_id
    task_description: str     # 用户描述的任务
    thread_id: str | None = None


class SynthesizeFromRecordingResponse(BaseModel):
    """从录制合成 Skill 的响应"""
    success: bool
    skill_id: int | None
    skill_name: str | None
    skill_yaml: str | None
    error: str | None
    processing_time_seconds: float
    frames_analyzed: int
    events_processed: int


@router.post("/skills/synthesize-from-recording", response_model=SynthesizeFromRecordingResponse)
async def synthesize_from_recording(request: SynthesizeFromRecordingRequest):
    """
    从视频录制同步合成 Skill（多模态版本）

    流程：
    1. 根据 session_id 获取事件序列
    2. 从视频提取关键帧
    3. 压缩帧并归一化坐标
    4. 调用 Kimi 多模态 LLM 分析
    5. 解析并保存 Skill

    **注意**：此 API 是同步的，处理时间约 10-60 秒，请设置合适的客户端超时。
    """
    import time
    start_time = time.time()

    logger.info(f"Received synthesis request: session={request.session_id}, video={request.video_path}")

    try:
        # 验证视频文件存在
        if not os.path.exists(request.video_path):
            raise HTTPException(
                status_code=400,
                detail=f"Video file not found: {request.video_path}"
            )

        # 创建合成器
        synthesizer = MultimodalSkillSynthesizer()

        # 构建录制会话
        recording = RecordingSession(
            video_path=request.video_path,
            session_id=request.session_id,
            task_description=request.task_description,
            thread_id=request.thread_id
        )

        # 执行合成
        result = await synthesizer.synthesize(recording)
        skill_data = result["skill"]
        metadata = result["metadata"]

        # 保存到数据库
        async with session_scope() as db:
            # 处理名称冲突
            base_name = skill_data["name"]
            unique_name = base_name
            counter = 1

            while True:
                stmt = select(LearnedSkill).where(LearnedSkill.name == unique_name)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if not existing:
                    break
                unique_name = f"{base_name}_{counter}"
                counter += 1

            if unique_name != base_name:
                logger.info(f"Skill name collision resolved: {base_name} -> {unique_name}")
                skill_data["name"] = unique_name

            # 创建 Skill 记录
            db_skill = LearnedSkill(
                name=skill_data["name"],
                description=skill_data["description"],
                namespace=skill_data.get("namespace", "misc"),
                trigger_patterns=json.dumps(skill_data.get("trigger_patterns", [])),
                parameters=json.dumps(skill_data.get("parameters", [])),
                instructions=skill_data["instructions"],
                source_session_id=skill_data.get("source_session_id"),
                source_thread_id=skill_data.get("source_thread_id"),
                skill_source="multimodal_record",
                status="draft",
                is_active=True,
                execution_mode=skill_data.get("execution_mode", "agentic"),
                macro_script=skill_data.get("macro_script"),
            )
            db.add(db_skill)
            await db.flush()

            # 生成 YAML 输出
            skill_yaml = f"""---
name: {skill_data['name']}
namespace: {skill_data.get('namespace', 'misc')}
description: {skill_data['description']}
trigger_patterns: {json.dumps(skill_data.get('trigger_patterns', []))}
parameters: {json.dumps(skill_data.get('parameters', []))}
---

{skill_data['instructions']}
"""

            processing_time = time.time() - start_time

            return SynthesizeFromRecordingResponse(
                success=True,
                skill_id=db_skill.id,
                skill_name=skill_data["name"],
                skill_yaml=skill_yaml,
                error=None,
                processing_time_seconds=round(processing_time, 2),
                frames_analyzed=metadata["frames_analyzed"],
                events_processed=metadata["events_processed"]
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Multimodal synthesis failed: {e}")
        processing_time = time.time() - start_time
        return SynthesizeFromRecordingResponse(
            success=False,
            skill_id=None,
            skill_name=None,
            skill_yaml=None,
            error=str(e),
            processing_time_seconds=round(processing_time, 2),
            frames_analyzed=0,
            events_processed=0
        )


@router.get("/skills/synthesize-from-recording/preview")
async def preview_recording_data(
    session_id: str,
    video_path: str
):
    """
    预览录制数据（调试用）

    返回关键帧提取计划和事件统计，不实际调用 LLM。
    """
    from app.core.learning.multimodal_synthesizer import MultimodalSkillSynthesizer
    from app.core.learning.frame_compressor import KeyframeSelector

    try:
        # 获取视频信息
        synthesizer = MultimodalSkillSynthesizer()
        video_info = await synthesizer._get_video_info(video_path)

        # 获取事件
        events = await synthesizer._fetch_events(session_id)

        # 预览关键帧选择
        selector = KeyframeSelector()
        keyframes = selector.select_keyframes(
            events=events,
            video_duration=video_info.duration,
            video_resolution=(video_info.width, video_info.height)
        )

        return {
            "video_info": {
                "path": video_path,
                "duration": video_info.duration,
                "resolution": f"{video_info.width}x{video_info.height}",
                "fps": video_info.fps,
            },
            "events": {
                "total": len(events),
                "types": list(set(e.action_type for e in events)),
            },
            "keyframes": {
                "planned": len(keyframes),
                "est_frames": min(len(keyframes), 15),
                "est_tokens": f"~{len(keyframes) * 1000}-{len(keyframes) * 1500}",
                "details": [
                    {
                        "timestamp": k.timestamp,
                        "context": k.context,
                        "description": k.description,
                        "priority": k.priority,
                    }
                    for k in keyframes[:5]  # 只显示前5个
                ],
            },
        }

    except Exception as e:
        logger.exception(f"Preview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Smart Replay Synthesis ============

class AnnotationCreate(BaseModel):
    """创建标注请求"""
    session_id: str
    thread_id: str | None = None
    annotation_type: str = "extract_region"  # extract_region, click_point, task_boundary
    video_timestamp_ms: int
    frame_number: int | None = None
    region_x: float | None = None
    region_y: float | None = None
    region_width: float | None = None
    region_height: float | None = None
    related_event_id: int | None = None
    user_note: str | None = None


class AnnotationResponse(BaseModel):
    """标注响应"""
    id: int
    session_id: str
    annotation_type: str
    video_timestamp_ms: int
    region: dict | None
    user_note: str | None
    created_at: datetime


class SmartSynthesisRequest(BaseModel):
    """智能合成请求"""
    session_id: str
    thread_id: str | None = None
    task_goal: str
    annotation_ids: list[int] | None = None  # 指定使用哪些标注，null表示使用全部


class SmartSynthesisResponse(BaseModel):
    """智能合成响应"""
    job_id: int
    status: str
    message: str


class SynthesisJobResponse(BaseModel):
    """合成任务状态响应"""
    id: int
    session_id: str
    status: str
    progress_percent: int
    current_phase: str | None
    task_goal: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result: dict | None  # 完成后包含 generated_skill
    error: dict | None  # 失败时包含错误信息


@router.post("/recordings/annotations", response_model=AnnotationResponse)
async def create_annotation(body: AnnotationCreate):
    """
    创建录制标注

    用户在回放视频时框选的数据区域。
    """

    async with session_scope() as db:
        annotation = RecordingAnnotation(
            session_id=body.session_id,
            thread_id=body.thread_id,
            annotation_type=body.annotation_type,
            video_timestamp_ms=body.video_timestamp_ms,
            frame_number=body.frame_number,
            region_x=body.region_x,
            region_y=body.region_y,
            region_width=body.region_width,
            region_height=body.region_height,
            related_event_id=body.related_event_id,
            user_note=body.user_note,
        )
        db.add(annotation)
        await db.flush()
        await db.refresh(annotation)

        return AnnotationResponse(
            id=annotation.id,
            session_id=annotation.session_id,
            annotation_type=annotation.annotation_type,
            video_timestamp_ms=annotation.video_timestamp_ms,
            region={
                "x": annotation.region_x,
                "y": annotation.region_y,
                "width": annotation.region_width,
                "height": annotation.region_height,
            } if annotation.region_x is not None else None,
            user_note=annotation.user_note,
            created_at=annotation.created_at,
        )


@router.get("/recordings/{session_id}/annotations", response_model=list[AnnotationResponse])
async def list_annotations(session_id: str):
    """
    获取录制的所有标注
    """
    from sqlalchemy import select

    async with session_scope() as db:
        stmt = select(RecordingAnnotation).where(
            RecordingAnnotation.session_id == session_id
        ).order_by(RecordingAnnotation.video_timestamp_ms)

        result = await db.execute(stmt)
        annotations = result.scalars().all()

        return [
            AnnotationResponse(
                id=a.id,
                session_id=a.session_id,
                annotation_type=a.annotation_type,
                video_timestamp_ms=a.video_timestamp_ms,
                region={
                    "x": a.region_x,
                    "y": a.region_y,
                    "width": a.region_width,
                    "height": a.region_height,
                } if a.region_x is not None else None,
                user_note=a.user_note,
                created_at=a.created_at,
            )
            for a in annotations
        ]


@router.delete("/recordings/annotations/{annotation_id}")
async def delete_annotation(annotation_id: int):
    """
    删除标注
    """
    from sqlalchemy import select

    async with session_scope() as db:
        stmt = select(RecordingAnnotation).where(RecordingAnnotation.id == annotation_id)
        result = await db.execute(stmt)
        annotation = result.scalar_one_or_none()

        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation not found")

        await db.delete(annotation)

    return {"success": True, "message": "Annotation deleted"}


@router.post("/recordings/{session_id}/smart-synthesis", response_model=SmartSynthesisResponse)
async def start_smart_synthesis(
    session_id: str,
    body: SmartSynthesisRequest,
    background_tasks: BackgroundTasks
):
    """
    启动智能合成任务

    基于用户标注和任务目标，异步进行 LLM 推理生成技能。
    """
    from sqlalchemy import select

    # 验证 session 存在
    async with session_scope() as db:
        # 获取使用的标注
        if body.annotation_ids:
            stmt = select(RecordingAnnotation).where(
                RecordingAnnotation.id.in_(body.annotation_ids)
            )
        else:
            stmt = select(RecordingAnnotation).where(
                RecordingAnnotation.session_id == session_id
            )

        result = await db.execute(stmt)
        annotations = result.scalars().all()

        if not annotations:
            raise HTTPException(
                status_code=400,
                detail="No annotations found for synthesis"
            )

        # 创建合成任务
        job = SynthesisJob(
            session_id=session_id,
            thread_id=body.thread_id,
            task_goal=body.task_goal,
            annotation_ids=[a.id for a in annotations],
            status="pending",
            progress_percent=0,
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)

        # 启动后台任务
        background_tasks.add_task(
            run_smart_synthesis,
            job_id=job.id,
            session_id=session_id,
            thread_id=body.thread_id,
            task_goal=body.task_goal,
            annotation_ids=[a.id for a in annotations],
        )

        return SmartSynthesisResponse(
            job_id=job.id,
            status="pending",
            message=f"Synthesis job started with {len(annotations)} annotations",
        )


async def run_smart_synthesis(
    job_id: int,
    session_id: str,
    thread_id: str | None,
    task_goal: str,
    annotation_ids: list[int],
):
    """
    后台运行智能合成
    """
    from app.core.learning.smart_synthesizer import SmartSynthesizer
    from sqlalchemy import select

    async with session_scope() as db:
        # 更新任务状态为 processing
        stmt = select(SynthesisJob).where(SynthesisJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one()
        job.status = "processing"
        job.started_at = datetime.now()
        await db.commit()

    try:
        # 获取标注详情
        async with session_scope() as db:
            stmt = select(RecordingAnnotation).where(
                RecordingAnnotation.id.in_(annotation_ids)
            )
            result = await db.execute(stmt)
            annotations = result.scalars().all()

        # 运行合成器
        synthesizer = SmartSynthesizer(
            job_id=job_id,
            session_id=session_id,
            thread_id=thread_id,
            task_goal=task_goal,
            annotations=list(annotations),
        )

        skill = await synthesizer.synthesize()

        # 保存结果
        async with session_scope() as db:
            stmt = select(SynthesisJob).where(SynthesisJob.id == job_id)
            result = await db.execute(stmt)
            job = result.scalar_one()

            job.status = "completed"
            job.progress_percent = 100
            job.completed_at = datetime.now()
            skill_dict = skill.to_dict() if hasattr(skill, 'to_dict') else {
                "name": skill.name,
                "description": skill.description,
                "namespace": skill.namespace,
                "trigger_patterns": skill.trigger_patterns,
                "instructions": skill.instructions,
                "execution_mode": skill.execution_mode,
                "macro_script": skill.macro_script,
            }
            job.generated_skill = skill_dict

            # 保存到 LearnedSkill 表
            try:
                import json
                new_skill = LearnedSkill(
                    name=skill.name,
                    description=skill.description,
                    namespace=skill.namespace or "misc",
                    trigger_patterns=json.dumps(skill.trigger_patterns) if skill.trigger_patterns else "[]",
                    parameters="[]",  # 默认空参数列表
                    instructions=skill.instructions,
                    execution_mode=skill.execution_mode,
                    macro_script=skill.macro_script,
                    is_active=True,
                    status="draft",  # 新生成的技能为草稿状态，需要审核
                    skill_source="smart_replay",  # 标识来源为智能回放合成
                )
                db.add(new_skill)
                await db.flush()  # 获取 ID
                job.skill_id = new_skill.id
                logger.info(f"[Job {job_id}] Saved skill to LearnedSkill: {new_skill.id} - {skill.name}")
            except Exception as e:
                logger.warning(f"[Job {job_id}] Failed to save skill to LearnedSkill: {e}")
                # 不影响主流程，继续提交

            await db.commit()

    except Exception as e:
        logger.exception(f"Smart synthesis failed for job {job_id}: {e}")

        async with session_scope() as db:
            stmt = select(SynthesisJob).where(SynthesisJob.id == job_id)
            result = await db.execute(stmt)
            job = result.scalar_one()

            job.status = "failed"
            job.error_message = str(e)
            job.error_traceback = traceback.format_exc()
            job.completed_at = datetime.now()
            await db.commit()


@router.get("/synthesis-jobs/{job_id}", response_model=SynthesisJobResponse)
async def get_synthesis_job(job_id: int):
    """
    获取合成任务状态和结果
    """
    from sqlalchemy import select

    async with session_scope() as db:
        stmt = select(SynthesisJob).where(SynthesisJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(status_code=404, detail="Synthesis job not found")

        return SynthesisJobResponse(
            id=job.id,
            session_id=job.session_id,
            status=job.status,
            progress_percent=job.progress_percent,
            current_phase=job.current_phase,
            task_goal=job.task_goal,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result={
                "skill": job.generated_skill,
                "insights": job.extracted_insights,
            } if job.generated_skill else None,
            error={
                "message": job.error_message,
                "traceback": job.error_traceback,
            } if job.error_message else None,
        )


@router.get("/recordings/{session_id}/synthesis-jobs", response_model=list[SynthesisJobResponse])
async def list_session_synthesis_jobs(session_id: str):
    """
    获取录制的所有合成任务
    """
    from sqlalchemy import select

    async with session_scope() as db:
        stmt = select(SynthesisJob).where(
            SynthesisJob.session_id == session_id
        ).order_by(SynthesisJob.created_at.desc())

        result = await db.execute(stmt)
        jobs = result.scalars().all()

        return [
            SynthesisJobResponse(
                id=j.id,
                session_id=j.session_id,
                status=j.status,
                progress_percent=j.progress_percent,
                current_phase=j.current_phase,
                task_goal=j.task_goal,
                created_at=j.created_at,
                started_at=j.started_at,
                completed_at=j.completed_at,
                result={"skill": j.generated_skill} if j.generated_skill else None,
                error={"message": j.error_message} if j.error_message else None,
            )
            for j in jobs
        ]
