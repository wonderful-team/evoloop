"""
Learning API Routes.
Handles human-in-the-loop requests and imitation learning endpoints.
"""
import json
import logging
import math
import os
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_, func, select, update

from app.utils.yaml import macro_from_yaml, macro_to_yaml, YAMLError, validate_macro_yaml

from app.core.engine.background_agent import run_agent_background
from app.core.execution.macro.service import MacroService
from app.core.learning.discovery import skill_discovery
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
    execution_mode: str | None = None  # Optional: override skill's execution mode


class RespondRequest(BaseModel):
    response: Any


class RespondResponse(BaseModel):
    success: bool
    message: str


class StartMirrorRequest(BaseModel):
    device_id: str
    record_video: bool = True


class StopMirrorRequest(BaseModel):
    session_id: str


class StartMirrorRecordingRequest(BaseModel):
    """[NEW] Request to start event recording for an active mirror session."""
    session_id: str


class PersistMirrorEventsRequest(BaseModel):
    """请求模型：持久化存储镜像事件"""
    session_id: str
    thread_id: str | None = None  # [NEW] Optional thread binding


class GlobalEventData(BaseModel):
    """全局桌面事件数据"""
    timestamp: float
    event_type: str  # "mouse_click", "key_press"
    key: str | None = None
    mouse_button: str | None = None
    position: tuple[float, float] | None = None
    window_title: str | None = None
    app_name: str | None = None
    process_id: int | None = None
    source: str | None = None # [NEW] Optional source override (e.g. "mobile" for mirror clicks)


class GlobalEventsRequest(BaseModel):
    """请求模型：接收全局桌面事件"""
    session_id: str
    thread_id: str
    events: list[GlobalEventData]


class DomEventData(BaseModel):
    """DOM 事件数据"""
    timestamp: float
    event_type: str  # "click", "input", "scroll", etc.
    selector: str | None = None
    target_text: str | None = None
    value: str | None = None
    url: str | None = None
    xpath: str | None = None
    coordinates: dict | None = None  # {x, y, width, height}


class DomEventsRequest(BaseModel):
    """请求模型：接收 DOM 事件"""
    session_id: str
    thread_id: str
    events: list[DomEventData]


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
    macro_script: str | None = None  # YAML format
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
async def list_pending_requests(thread_id: str | None = None):
    """
    Get all pending human input requests.
    Optionally filter by thread_id.
    """
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
async def get_request(request_id: str):
    """
    Get a specific human input request by ID.
    """
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


@router.post("/human-requests/{request_id}/respond", response_model=RespondResponse)
async def respond_to_request(request_id: str, body: RespondRequest):
    """
    Submit a response to a pending human input request.
    This will resume the paused agent workflow.
    """
    request = await get_pending_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.status != "pending":
        raise HTTPException(
            status_code=400, detail=f"Request is not pending (status: {request.status})"
        )

    success = await complete_request(request_id, body.response)

    if success:
        return RespondResponse(
            success=True, message=f"Response recorded for request {request_id}"
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to complete request")


@router.post("/human-requests/{request_id}/cancel", response_model=RespondResponse)
async def cancel_pending_request(request_id: str):
    """
    Cancel a pending human input request.
    The agent will receive the default value if set.
    """
    request = await get_pending_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.status != "pending":
        raise HTTPException(
            status_code=400, detail=f"Request is not pending (status: {request.status})"
        )

    success = await cancel_request(request_id)

    if success:
        return RespondResponse(success=True, message=f"Request {request_id} cancelled")
    else:
        raise HTTPException(status_code=500, detail="Failed to cancel request")


@router.post("/cleanup", response_model=RespondResponse)
async def cleanup_requests(max_age_hours: int = 24):
    """
    Clean up old completed/cancelled requests.
    """
    await cleanup_old_requests(max_age_hours)
    return RespondResponse(success=True, message="Cleanup completed")


# ============ Trace Recording API (Phase 1) ============


class StartRecordingRequest(BaseModel):
    thread_id: str
    task_name: str | None = None


class StartRecordingResponse(BaseModel):
    session_id: str
    message: str


class StopRecordingResponse(BaseModel):
    session_id: str
    event_count: int
    message: str


# In-memory session tracking
_active_sessions: dict[str, dict] = {}


class UploadScreenshotResponse(BaseModel):
    success: bool
    path: str
    message: str


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
                is_active=False,
                status="pending_review",
                instructions=skill.instructions,
                execution_mode=skill.execution_mode,
                macro_script=skill.macro_script,  # Already YAML string
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
    finally:
        # Always reload cache after potential synthesis
        await skill_discovery.reload()


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
    finally:
        await skill_discovery.reload()


@router.get("/skills", response_model=PaginatedSkillsResponse)
async def list_skills(
    active_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """
    List all learned skills with pagination.
    """
    # Trigger sync to ensure we show the latest skills from disk
    try:
        await skill_discovery._sync_system_skills()
    except Exception as e:
        logger.warning(f"Background skill sync failed during list: {e}")

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
                    "macro_script": s.macro_script or "",
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
            "macro_script": skill.macro_script or "",
            "validation_report": skill.validation_report,
            "instructions": skill.instructions,
            "resource_path": skill.resource_path,
        }


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: int):
    """
    Physically delete a skill and its resources.
    """
    try:
        async with session_scope() as db:
            # 1. Get Skill
            stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
            result = await db.execute(stmt)
            skill = result.scalar_one_or_none()

            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")

            # 2. Cleanup Resources on Disk (Phase 5 folders)
            if skill.resource_path:
                try:
                    path = Path(skill.resource_path)
                    if path.exists() and path.is_dir():
                        shutil.rmtree(path)
                        logger.info(f"Deleted skill resources at: {path}")
                except Exception as e:
                    logger.error(f"Failed to delete skill resources at {skill.resource_path}: {e}")

            # 3. Physical Delete from DB
            await db.delete(skill)
            await db.flush()
            
        return {"success": True, "message": f"Skill {skill_id} physically deleted"}
    finally:
        # 4. Invalidate Cache
        await skill_discovery.reload()


class UpdateSkillRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    namespace: str | None = None
    trigger_patterns: list[str] | None = None
    parameters: list[dict[str, Any]] | None = None
    instructions: str | None = None
    preconditions: list[dict[str, Any]] | None = None
    execution_mode: str | None = None
    macro_script: str | None = None  # YAML format


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: int, body: UpdateSkillRequest):
    """
    Update a learned skill.
    """
    try:
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
                # Validate it's valid YAML before saving
                try:
                    macro_from_yaml(body.macro_script)
                    skill.macro_script = body.macro_script
                except YAMLError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

            # 3. Commit (Automatic via session_scope exit, but we want to return updated data)
            await db.flush()
            
        return {
            "success": True,
            "message": f"Skill {skill_id} updated",
            "skill": {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "trigger_patterns": json.loads(skill.trigger_patterns) if skill.trigger_patterns else [],
                "parameters": json.loads(skill.parameters) if skill.parameters else [],
            },
        }
    finally:
        # 4. Invalidate Cache
        await skill_discovery.reload()


async def execute_macro_with_fallback(
    thread_id: str, 
    project_id: int, 
    skill: LearnedSkill, 
    macro_payload: list, 
    params: dict
):
    """
    Execute a deterministic macro with unified self-healing policy.
    
    Args:
        thread_id: Conversation thread ID
        project_id: Project ID
        skill: The LearnedSkill being executed (contains self-healing settings)
        macro_payload: Macro script steps
        params: Execution parameters
    """
    from app.core.execution.macro.healing_policy import SelfHealingPolicy
    
    # Prepare execution params with metadata
    execution_params = params.copy() if params else {}
    execution_params["_skill_id"] = skill.id
    execution_params["_skill_name"] = skill.name
    
    # Pass skill to MacroService for unified policy enforcement
    result = await MacroService.run(
        thread_id=thread_id, 
        script_input=macro_payload, 
        params=execution_params,
        skill=skill
    )
    
    # Check if fallback is needed
    if result.get("status") != "fallback_required":
        return
    
    # Check if self-healing is allowed (unified policy already checked in MacroService)
    if not result.get("allow_self_healing", True):
        logger.warning(
            f"[{thread_id}] Macro failed, but Self-Healing is DISABLED "
            f"(reason: {result.get('healing_disabled_reason', 'unknown')}). "
            f"Skipping fallback."
        )
        return

    logger.warning(f"[{thread_id}] Macro failed, triggering Agentic Fallback...")
    fallback_ctx = result.get("fallback_context", {})
    
    fallback_msg = (
        f"SYSTEM ALERT: The deterministic macro for '{skill.name}' failed.\n"
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
            "original_skill_id": skill.id,
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
    # Use provided execution_mode from request, fallback to skill's execution_mode
    execution_mode = body.execution_mode or skill.execution_mode
    
    if execution_mode == "deterministic" and skill.macro_script:
        import copy
        
        # Parse YAML to Python objects for execution
        try:
            macro_steps = macro_from_yaml(skill.macro_script)
        except YAMLError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse macro YAML: {e}")
        
        # Deepcopy to avoid mutating
        macro_payload = copy.deepcopy(macro_steps)
        bg_tasks.add_task(
            execute_macro_with_fallback, 
            thread_id=body.thread_id, 
            project_id=body.project_id or 1,
            skill=skill,  # Pass full skill object for unified policy
            macro_payload=macro_payload, 
            params=body.params
        )
        return {"success": True, "message": f"Deterministic Macro execution queued for '{skill_name}'", "execution_mode": execution_mode}
    else:
        # Fallback to Agentic mode
        inputs = {
            "messages": [{"type": "human", "content": directive}],
            "project_id": body.project_id,
        }
        bg_tasks.add_task(run_agent_background, body.thread_id, inputs)
    
        return {"success": True, "message": f"Agentic execution queued for '{skill_name}'", "execution_mode": execution_mode}


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
    session = await mirror_manager.create_session(body.device_id, record_video=body.record_video)
    if not session.is_active:
        raise HTTPException(status_code=500, detail=session.error or "Failed to start mirroring session")

    # Register in active sessions so /traces/events can accept events for this session
    _active_sessions[session.session_id] = {
        "thread_id": "global",
        "task_name": f"Android Mirror ({body.device_id})",
        "started_at": datetime.utcnow(),
        "event_count": 0,
    }

    return {
        "success": True,
        "session_id": session.session_id,
        "device_id": session.device_id
    }


@router.post("/mirror/start-recording")
async def start_mirror_recording(body: StartMirrorRecordingRequest):
    """
    [NEW] Start event recording for an active mirror session.
    Called when user clicks 'Start Recording' button.
    """
    logger.info(f"[API] Received start-recording request for session: {body.session_id}")
    success = mirror_manager.start_recording(body.session_id)
    logger.info(f"[API] start_recording result: {success}")
    if not success:
        raise HTTPException(status_code=400, detail="Failed to start recording. Session may not be active or recording already started.")

    return {
        "success": True,
        "message": "Recording started",
        "session_id": body.session_id
    }


@router.post("/mirror/stop")
async def stop_mirror_session(body: StopMirrorRequest):
    """
    Stop an active mirroring session.

    [v3 Unified] Events are now persisted in real-time during recording,
    so this endpoint no longer needs to persist events on stop.
    """
    result = mirror_manager.stop_session(body.session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # [v3] Events are persisted in real-time during recording
    # [v3] Query database for total count of all events (ADB + DOM/Marker + Global)
    # This ensures "No operation captured" doesn't trigger if only regions were marked
    async with session_scope() as db:
        stmt = select(func.count(TraceEvent.id)).where(
            TraceEvent.recording_session_id == body.session_id
        )
        total_count_result = await db.execute(stmt)
        total_count = total_count_result.scalar() or 0

    return {
        "success": True,
        "message": "Mirroring session stopped",
        "video_path": result.get("video_path"),
        "session_id": result.get("session_id"),
        "event_count": total_count
    }


@router.get("/mirror/device/{device_id}/resolution")
async def get_device_resolution(device_id: str):
    """Get Android device screen resolution via ADB."""
    from app.infrastructure.drivers.adb import adb_driver
    try:
        size = adb_driver.get_screen_size(device_id)
        if not size:
            return {"width": 1080, "height": 1920}  # Sensible fallback
        return {"width": size[0], "height": size[1]}
    except Exception as e:
        logger.error(f"Failed to get device resolution: {e}")
        return {"width": 1080, "height": 1920}


@router.post("/mirror/events")
async def persist_mirror_events(body: PersistMirrorEventsRequest):
    """
    [v3 Unified] Persist Android mirror events to backend.

    [NOTE] With v3 unified architecture, events are now persisted in real-time
    during recording via _persist_loop(). This endpoint serves as:
    1. A final flush/confirmation for any remaining buffered events
    2. A retry mechanism in case of network issues during recording

    Called when user confirms skill synthesis (recommended for data integrity).
    """
    # Get events from session (may include any not yet persisted)
    events = mirror_manager.get_session_events(body.session_id)
    if not events:
        return {"success": True, "message": "No events to persist (already persisted in real-time)", "count": 0}

    # Check if events are already in DB (real-time persistence succeeded)
    async with session_scope() as db:
        stmt = select(TraceEvent).where(TraceEvent.recording_session_id == body.session_id)
        result = await db.execute(stmt)
        existing_count = len(result.scalars().all())

        if existing_count >= len(events):
            logger.info(f"[persist_mirror_events] Events already persisted ({existing_count} in DB vs {len(events)} in session)")
            return {"success": True, "message": "Events already persisted in real-time", "count": existing_count}

    # Persist any missing events
    try:
        async with session_scope() as db:
            for i, event_data in enumerate(events):
                payload_data = event_data.get("payload", {})

                # event_data["timestamp"] is relative milliseconds from video recording start
                relative_ms = event_data.get("timestamp", 0)

                node_name = event_data.get("node_name") or payload_data.get("device_id") or "android_mirror"
                source = event_data.get("source") or "mobile"
                thread_id = body.thread_id or "global"

                trace_event = TraceEvent(
                    session_id=body.session_id,
                    recording_session_id=body.session_id,
                    thread_id=thread_id,
                    step_number=i,
                    node_name=node_name,
                    action_type="user_interaction",
                    timestamp=relative_ms,  # Relative milliseconds from video start
                    event_type=event_data["event_type"],
                    target_selector=event_data.get("target_selector"),
                    target_text=event_data.get("target_text"),
                    payload=payload_data,
                    mouse_x=payload_data.get("x"),
                    mouse_y=payload_data.get("y"),
                    source=source,
                    app_name=payload_data.get("package_name"),
                    state_snapshot=json.dumps({"context": "android_mirror"}),
                    action_payload=json.dumps(payload_data)
                )
                db.add(trace_event)

                # [NEW] Log first few events for debugging
                if i < 5:
                    logger.info(f"[persist_mirror_events] Event {i}: {event_data['event_type']} at {relative_ms}ms, "
                                f"device_id={payload_data.get('device_id')}, "
                                f"package={payload_data.get('package_name')}, "
                                f"coords=({payload_data.get('x')}, {payload_data.get('y')})")

        return {"success": True, "message": "Events persisted", "count": len(events)}
    except Exception as e:
        logger.exception(f"Failed to persist mirror events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to persist events: {str(e)}")


@router.post("/global/events")
async def persist_global_events(body: GlobalEventsRequest):
    """
    Persist global desktop events to backend (real-time/batched persistence).
    Unified with mirror events - all events go to TraceEvent table.
    """
    if not body.events:
        return {"success": True, "message": "No events to persist", "count": 0}

    try:
        async with session_scope() as db:
            for i, event in enumerate(body.events):
                # Build payload with all available data
                payload = {
                    "key": event.key,
                    "mouse_button": event.mouse_button,
                    "position": event.position,
                    "process_id": event.process_id,
                    "platform": "macos",
                    "relative_timestamp_ms": int(event.timestamp),
                }
                # Remove None values
                payload = {k: v for k, v in payload.items() if v is not None}
                
                # [v3] Standardize source and app name
                source = event.source or "global"
                app_name = event.app_name
                
                # [FIX] For mobile events, sync package name from mirror session
                if source == "mobile":
                    session = mirror_manager.get_session(body.session_id)
                    if session:
                        resolved_pkg = session.get_current_package()
                        if resolved_pkg:
                            app_name = resolved_pkg
                
                # Ensure package_name is also in the payload for downstream consumers (like synthesizer)
                if app_name:
                    payload["package_name"] = app_name

                trace_event = TraceEvent(
                    session_id=body.session_id,
                    recording_session_id=body.session_id,
                    thread_id=body.thread_id,
                    step_number=i,
                    node_name=app_name or "global_recorder",
                    action_type="user_interaction",
                    timestamp=int(event.timestamp),  # Relative milliseconds
                    event_type=event.event_type,
                    target_selector=f"global://screen/{event.position[0]}/{event.position[1]}" if event.position else None,
                    target_text=event.window_title,
                    payload=payload,
                    mouse_x=event.position[0] if event.position else None,
                    mouse_y=event.position[1] if event.position else None,
                    source=source,
                    app_name=app_name,
                    window_title=event.window_title,
                    state_snapshot=json.dumps({"context": "global_recorder"}),
                    action_payload=json.dumps(payload)
                )
                db.add(trace_event)

                if i < 5:
                    logger.info(f"[persist_global_events] Event {i}: {event.event_type} at {int(event.timestamp)}ms, "
                                f"app={event.app_name}, window={event.window_title}")

        return {"success": True, "message": "Global events persisted", "count": len(body.events)}
    except Exception as e:
        logger.exception(f"Failed to persist global events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to persist events: {str(e)}")


@router.post("/dom/events")
async def persist_dom_events(body: DomEventsRequest):
    """
    Persist DOM events to backend (real-time/batched persistence).
    Unified with mirror events - all events go to TraceEvent table.
    """
    if not body.events:
        return {"success": True, "message": "No events to persist", "count": 0}

    try:
        async with session_scope() as db:
            for i, event in enumerate(body.events):
                # Build payload with all available data
                payload = {
                    "value": event.value,
                    "url": event.url,
                    "xpath": event.xpath,
                    "coordinates": event.coordinates,
                    "platform": "web",
                    "relative_timestamp_ms": int(event.timestamp),
                }
                # Remove None values
                payload = {k: v for k, v in payload.items() if v is not None}

                is_region_extract = event.event_type == "region_extract"
                action_type = "region_extract" if is_region_extract else "user_interaction"
                node_name = "region_marker" if is_region_extract else "dom_recorder"

                trace_event = TraceEvent(
                    session_id=body.session_id,
                    recording_session_id=body.session_id,
                    thread_id=body.thread_id,
                    step_number=i,
                    node_name=node_name,
                    action_type=action_type,
                    timestamp=int(event.timestamp),  # Relative milliseconds
                    event_type=event.event_type,
                    target_selector=event.selector,
                    target_text=event.target_text,
                    payload=payload,
                    source="dom",
                    app_name=event.url if not is_region_extract else "screen_region",  # URL as app_name for web
                    state_snapshot=json.dumps({"context": node_name, "url": event.url}),
                    action_payload=json.dumps(payload)
                )
                db.add(trace_event)

                if i < 5:
                    logger.info(f"[persist_dom_events] Event {i}: {event.event_type} at {int(event.timestamp)}ms, "
                                f"selector={event.selector}, url={event.url}")

        return {"success": True, "message": "DOM events persisted", "count": len(body.events)}
    except Exception as e:
        logger.exception(f"Failed to persist DOM events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to persist events: {str(e)}")


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
    """从录制合成 Skill 的请求（v3 统一版）

    [v3 统一架构] 所有录制类型（Desktop/Global/Android）的事件都已通过
    实时 API（/global/events, /dom/events, /mirror/events）持久化到数据库，
    合成时统一从数据库读取，不再支持通过请求体传入事件。
    """
    video_path: str           # Tauri 返回的视频文件路径
    session_id: str           # 关联事件的 session_id（用于从数据库查询事件）
    task_description: str     # 用户描述的任务
    thread_id: str | None = None


class SynthesizeFromRecordingResponse(BaseModel):
    """从录制合成 Skill 的响应"""
    success: bool
    skill_id: int | None
    skill_name: str | None
    skill_yaml: str | None
    macro_script: str | None = None  # YAML format
    verification: dict | None = None
    error: str | None
    processing_time_seconds: float
    frames_analyzed: int
    events_processed: int


@router.post("/skills/synthesize-from-recording", response_model=SynthesizeFromRecordingResponse)
async def synthesize_from_recording(request: SynthesizeFromRecordingRequest):
    """
    从视频录制同步合成 Skill（多模态版本 - v3 统一版）

    流程：
    1. 【统一】所有录制类型（Desktop/Global/Android）的事件都已通过实时接口持久化到数据库
    2. 【统一】合成器从数据库读取事件（按 session_id 查询）
    3. 从视频提取关键帧
    4. 压缩帧并归一化坐标
    5. 调用 Kimi 多模态 LLM 分析
    6. 解析并保存 Skill

    **注意**：此 API 是同步的，处理时间约 10-60 秒，请设置合适的客户端超时。

    **v3 变更**：
    - 所有录制类型统一使用实时事件持久化（/global/events, /dom/events, /mirror/events）
    - 合成时统一从数据库读取事件，不再依赖请求中的 events 参数
    - 移除了向后兼容的 events 参数处理
    """
    import time
    start_time = time.time()

    logger.info(f"[v3] Received synthesis request: session={request.session_id}, video={request.video_path}")

    try:
        # 验证视频文件存在
        if not os.path.exists(request.video_path):
            raise HTTPException(
                status_code=400,
                detail=f"Video file not found: {request.video_path}"
            )

        # [v3 统一] 事件已通过实时 API 持久化，直接读取数据库
        logger.info("[v3] Using unified flow: events will be read from database (already persisted via real-time API)")

        # 创建合成器
        synthesizer = MultimodalSkillSynthesizer()

        # 构建录制会话
        recording = RecordingSession(
            video_path=request.video_path,
            session_id=request.session_id,
            task_description=request.task_description,
            thread_id=request.thread_id
        )

        # 执行合成 (只合成，不执行验证，以便在验证失败时也能保存)
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
                status="pending_review", # [FIX] 需要用户二次确认
                is_active=True,
                execution_mode=skill_data.get("execution_mode", "agentic"),
                macro_script=skill_data.get("macro_script"),  # Should be YAML string from synthesizer
                validation_report={"status": "pending_verification"}, # 初始状态
            )
            db.add(db_skill)
            await db.flush()
            
            # [Fix 2] 在技能落库之后执行 Dry-run 验证
            verification = {"status": "skipped"}
            if db_skill.macro_script:
                try:
                    verification = await synthesizer.verify_macro(db_skill.macro_script)
                except Exception as e:
                    logger.error(f"Verification failed after saving DB: {e}")
                    verification = {
                        "status": "failed",
                        "error_message": str(e)
                    }
                
                # 更新验证结果
                db_skill.validation_report = verification
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
                macro_script=skill_data.get("macro_script"),  # Should be YAML string from synthesizer
                verification=verification,
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

class AnnotationResponse(BaseModel):
    """标注响应"""
    id: int
    session_id: str
    annotation_type: str
    video_timestamp_ms: int
    region: dict | None
    user_note: str | None
    created_at: datetime


class AndroidExtractPointRequest(BaseModel):
    """Android镜像实时提取点标记请求 - 支持区域标记"""
    session_id: str
    thread_id: str | None = None
    x: float  # 区域左上角 X 坐标（相对坐标 0-1）
    y: float  # 区域左上角 Y 坐标（相对坐标 0-1）
    width: float | None = None   # 区域宽度（相对坐标 0-1），null 表示单点标记
    height: float | None = None  # 区域高度（相对坐标 0-1），null 表示单点标记
    timestamp_ms: int | None = None  # 可选：录制时间戳
    note: str | None = None  # 可选：用户备注


class AndroidExtractPointResponse(BaseModel):
    """Android镜像提取点标记响应"""
    id: int
    session_id: str
    x: float
    y: float
    width: float | None  # 区域宽度（相对坐标 0-1）
    height: float | None  # 区域高度（相对坐标 0-1）
    timestamp_ms: int | None
    note: str | None
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


@router.get("/recordings/{session_id}/annotations", response_model=list[AnnotationResponse])
async def list_annotations(session_id: str):
    """
    获取录制的所有标注 (从 TraceEvent 表中查询 region_extract 类型事件)
    [Scheme A] 废弃 RecordingAnnotation 表，统一使用 TraceEvent
    """
    async with session_scope() as db:
        # [Scheme A] Query TraceEvent for region_extract events instead of RecordingAnnotation
        stmt = select(TraceEvent).where(
            TraceEvent.recording_session_id == session_id,
            TraceEvent.action_type == "region_extract"
        ).order_by(TraceEvent.timestamp)

        result = await db.execute(stmt)
        events = result.scalars().all()

        annotations = []
        for e in events:
            # Extract coordinates from payload
            coords = e.payload.get("coordinates") if e.payload else None
            annotations.append(
                AnnotationResponse(
                    id=e.id,
                    session_id=e.recording_session_id or session_id,
                    annotation_type="extract",
                    video_timestamp_ms=int(e.timestamp) if e.timestamp else 0,
                    region={
                        "x": coords.get("x") if coords else None,
                        "y": coords.get("y") if coords else None,
                        "width": coords.get("width") if coords else None,
                        "height": coords.get("height") if coords else None,
                    } if coords else None,
                    user_note=e.target_text or "Screen region extraction",
                    created_at=e.created_at if e.created_at else datetime.now(),
                )
            )

        return annotations


@router.post("/mirror/extract-point", response_model=AndroidExtractPointResponse)
async def create_android_extract_point(body: AndroidExtractPointRequest):
    """
    [Android Mirror] 实时标记数据提取点
    [Scheme A] 废弃 RecordingAnnotation 表，统一使用 TraceEvent

    在Android镜像录制过程中，用户通过悬浮按钮标记需要提取数据的屏幕位置。
    该API创建一个 TraceEvent (action_type="region_extract")，用于后续SmartReplay分析。

    用户通过悬浮按钮标记需要提取数据的屏幕位置，支持框选区域或单点标记。
    """
    import time
    from app.models import TraceEvent

    # 如果未提供时间戳，使用当前时间
    timestamp_ms = body.timestamp_ms or int(time.time() * 1000)

    async with session_scope() as db:
        # [Scheme A] 创建 TraceEvent 记录，action_type="region_extract"
        region_width = body.width if body.width is not None else 0.02  # 默认 2% 区域
        region_height = body.height if body.height is not None else 0.02

        trace_event = TraceEvent(
            session_id=body.session_id,
            recording_session_id=body.session_id,
            thread_id=body.thread_id,
            step_number=0,  # 由后续处理决定
            node_name="android_region_marker",
            action_type="region_extract",
            timestamp=timestamp_ms,
            event_type="region_extract",
            target_selector=f"android://screen/{body.x:.4f}/{body.y:.4f}",
            target_text=body.note or "Android镜像标记的数据提取点",
            payload={
                "coordinates": {
                    "x": body.x,
                    "y": body.y,
                    "width": region_width,
                    "height": region_height,
                },
                "platform": "android",
                "relative_timestamp_ms": timestamp_ms,
            },
            source="android",
            app_name="android_mirror",
            state_snapshot=json.dumps({"context": "android_region_marker"}),
            action_payload=json.dumps({
                "x": body.x,
                "y": body.y,
                "width": region_width,
                "height": region_height,
            }),
        )
        db.add(trace_event)
        await db.flush()
        await db.refresh(trace_event)

        region_type = "区域" if body.width and body.height else "单点"
        logger.info(f"[AndroidMirror] Extract point created: id={trace_event.id}, "
                   f"session={body.session_id}, pos=({body.x:.3f}, {body.y:.3f}), "
                   f"size=({region_width:.3f}, {region_height:.3f}), type={region_type}")

        return AndroidExtractPointResponse(
            id=trace_event.id,
            session_id=body.session_id,
            x=body.x,
            y=body.y,
            width=region_width,
            height=region_height,
            timestamp_ms=timestamp_ms,
            note=body.note or "Android镜像标记的数据提取点",
            created_at=trace_event.created_at,
        )


@router.get("/mirror/{session_id}/extract-points", response_model=list[AndroidExtractPointResponse])
async def list_android_extract_points(session_id: str):
    """
    [Android Mirror] 获取指定会话的所有提取点
    [Scheme A] 从 TraceEvent 表查询 region_extract 类型事件
    """
    from app.models import TraceEvent

    async with session_scope() as db:
        stmt = select(TraceEvent).where(
            TraceEvent.recording_session_id == session_id,
            TraceEvent.action_type == "region_extract"
        ).order_by(TraceEvent.timestamp)

        result = await db.execute(stmt)
        events = result.scalars().all()

        extract_points = []
        for e in events:
            coords = e.payload.get("coordinates") if e.payload else {}
            extract_points.append(
                AndroidExtractPointResponse(
                    id=e.id,
                    session_id=e.recording_session_id or session_id,
                    x=coords.get("x", 0) if coords else 0,
                    y=coords.get("y", 0) if coords else 0,
                    width=coords.get("width") if coords else None,
                    height=coords.get("height") if coords else None,
                    timestamp_ms=int(e.timestamp) if e.timestamp else 0,
                    note=e.target_text or "Android镜像标记的数据提取点",
                    created_at=e.created_at,
                )
            )

        return extract_points


@router.post("/recordings/{session_id}/smart-synthesis", response_model=SmartSynthesisResponse)
async def start_smart_synthesis(
    session_id: str,
    body: SmartSynthesisRequest,
    background_tasks: BackgroundTasks
):
    """
    启动智能合成任务

    基于用户标注和任务目标，异步进行 LLM 推理生成技能。
    [Scheme A] 使用 TraceEvent 替代 RecordingAnnotation，查询 action_type="region_extract" 的事件
    """
    from sqlalchemy import select

    # 验证 session 存在
    async with session_scope() as db:
        # [Scheme A] 从 TraceEvent 获取区域提取事件作为标注
        if body.annotation_ids:
            stmt = select(TraceEvent).where(
                TraceEvent.id.in_(body.annotation_ids),
                TraceEvent.action_type == "region_extract"
            )
        else:
            stmt = select(TraceEvent).where(
                TraceEvent.recording_session_id == session_id,
                TraceEvent.action_type == "region_extract"
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
    [Scheme A] 使用 TraceEvent 替代 RecordingAnnotation
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
        # [Scheme A] 从 TraceEvent 获取标注详情
        async with session_scope() as db:
            stmt = select(TraceEvent).where(
                TraceEvent.id.in_(annotation_ids),
                TraceEvent.action_type == "region_extract"
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
            skill_dict = skill if isinstance(skill, dict) else {
                "name": getattr(skill, 'name', 'unnamed_skill'),
                "description": getattr(skill, 'description', ''),
                "namespace": getattr(skill, 'namespace', 'misc'),
                "trigger_patterns": getattr(skill, 'trigger_patterns', []),
                "instructions": getattr(skill, 'instructions', ''),
                "execution_mode": getattr(skill, 'execution_mode', 'agentic'),
                "macro_script": getattr(skill, 'macro_script', ''),
            }
            job.generated_skill = skill_dict

            # 保存到 LearnedSkill 表
            try:
                new_skill = LearnedSkill(
                    name=skill_dict.get("name", "unnamed_skill"),
                    description=skill_dict.get("description", ""),
                    namespace=skill_dict.get("namespace", "misc"),
                    trigger_patterns=json.dumps(skill_dict.get("trigger_patterns", [])),
                    parameters="[]",
                    instructions=skill_dict.get("instructions", ""),
                    execution_mode=skill_dict.get("execution_mode", "agentic"),
                    macro_script=skill_dict.get("macro_script", ""),
                    is_active=False,
                    status="pending_review",
                    skill_source="smart_replay",
                )
                db.add(new_skill)
                await db.flush()  # 获取 ID
                job.skill_id = new_skill.id
                logger.info(f"[Job {job_id}] Saved skill to LearnedSkill: {new_skill.id} - {skill_dict.get('name')}")
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


@router.delete("/recordings/{session_id}")
async def cleanup_recording_session(
    session_id: str,
    video_path: str | None = None
):
    """
    清理录制会话的所有关联数据。

    包括：
    1. 删除 TraceEvent 中的事件记录（包括 region_extract 标注事件）
    2. 删除 SynthesisJob 记录
    3. 删除视频文件（如果提供路径）

    [Scheme A] 已废弃 RecordingAnnotation 表，标注数据统一存储在 TraceEvent 中
    """
    from sqlalchemy import select, delete
    import os

    deleted_counts = {
        "events": 0,
        "jobs": 0,
        "video_file": False
    }

    try:
        async with session_scope() as db:
            # 1. 删除 TraceEvent（包括所有事件和 region_extract 标注）
            stmt = delete(TraceEvent).where(
                or_(
                    TraceEvent.recording_session_id == session_id,
                    TraceEvent.session_id == session_id
                )
            )
            result = await db.execute(stmt)
            deleted_counts["events"] = getattr(result, "rowcount", 0)

            # 2. 删除 SynthesisJob
            stmt = delete(SynthesisJob).where(SynthesisJob.session_id == session_id)
            result = await db.execute(stmt)
            deleted_counts["jobs"] = getattr(result, "rowcount", 0)

        # 4. 删除视频文件
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                deleted_counts["video_file"] = True
                logger.info(f"[Cleanup] Deleted video file: {video_path}")
            except Exception as e:
                logger.error(f"[Cleanup] Failed to delete video file {video_path}: {e}")

        logger.info(f"[Cleanup] Session {session_id} cleaned up: {deleted_counts}")

        return {
            "success": True,
            "message": f"Recording session {session_id} cleaned up",
            "deleted": deleted_counts
        }
    except Exception as e:
        logger.exception(f"[Cleanup] Failed to cleanup session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.post("/skills/{skill_id}/confirm", response_model=RespondResponse)
async def confirm_learned_skill(skill_id: int):
    """
    [NEW] 用户确认合成的技能。
    将状态从 pending_review 更新为 verified。
    """
    async with session_scope() as db:
        stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
        skill = (await db.execute(stmt)).scalar_one_or_none()

        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if skill.status != "pending_review":
            return RespondResponse(
                success=False, 
                message=f"Skill is not in pending_review status (current: {skill.status})"
            )

        # 更新状态
        skill.status = "verified"
        skill.is_active = True
        
        # 记录日志
        logger.info(f"Skill {skill.id} ({skill.name}) confirmed by user.")
        
        return RespondResponse(
            success=True, 
            message=f"Skill '{skill.name}' confirmed and activated."
        )



# ============ YAML Macro Support (NEW) ============


class CreateSkillFromYamlRequest(BaseModel):
    """Request to create a skill from YAML macro definition."""
    name: str
    description: str | None = None
    namespace: str | None = None
    yaml_content: str


class ValidateYamlRequest(BaseModel):
    """Request to validate YAML macro format."""
    yaml_content: str


class ValidateYamlResponse(BaseModel):
    """Response from YAML validation."""
    valid: bool
    errors: list[str]
    step_count: int = 0


@router.post("/skills/from-yaml")
async def create_skill_from_yaml(
    body: CreateSkillFromYamlRequest,
    bg_tasks: BackgroundTasks
):
    """
    Create a new skill from YAML macro definition.
    
    The YAML should follow the EvoLoop macro format:
    ```yaml
    version: "1.0"
    metadata:
      format: evoloop-macro
    steps:
      - type: action
        event_type: navigate
        source: dom
        payload:
          url: "https://example.com"
    ```
    """
    try:
        # Validate YAML format first
        is_valid, errors = validate_macro_yaml(body.yaml_content)
        if not is_valid:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid YAML format: {'; '.join(errors)}"
            )
        
        macro_script = macro_from_yaml(body.yaml_content)
        
        async with session_scope() as db:
            # Check name uniqueness
            base_name = body.name
            unique_name = base_name
            counter = 1
            
            while True:
                stmt = select(LearnedSkill).where(LearnedSkill.name == unique_name)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if not existing:
                    break
                unique_name = f"{base_name}_{counter}"
                counter += 1
            
            skill = LearnedSkill(
                name=unique_name,
                description=body.description or f"Created from YAML ({len(macro_script)} steps)",
                namespace=body.namespace,
                macro_script=macro_script,
                execution_mode="deterministic",
                is_active=False,
                status="pending_review",
                trigger_patterns=json.dumps([unique_name.lower().replace(" ", "_")]),
                parameters=json.dumps([]),
                tools_used=json.dumps([]),
            )
            db.add(skill)
            await db.flush()
            
            return {
                "success": True, 
                "skill_id": skill.id,
                "skill_name": unique_name,
                "step_count": len(macro_script)
            }
            
    except YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML error: {str(e)}")
    except Exception as e:
        logger.exception(f"Failed to create skill from YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {str(e)}")


@router.post("/skills/validate-yaml", response_model=ValidateYamlResponse)
async def validate_skill_yaml(body: ValidateYamlRequest):
    """
    Validate YAML macro format without creating a skill.
    Useful for frontend validation before saving.
    """
    try:
        is_valid, errors = validate_macro_yaml(body.yaml_content)
        
        step_count = 0
        if is_valid:
            steps = macro_from_yaml(body.yaml_content)
            step_count = len(steps)
        
        return ValidateYamlResponse(
            valid=is_valid,
            errors=errors,
            step_count=step_count
        )
    except Exception as e:
        return ValidateYamlResponse(
            valid=False,
            errors=[str(e)],
            step_count=0
        )


@router.get("/skills/{skill_id}/yaml")
async def get_skill_yaml(skill_id: int):
    """
    Get skill macro as YAML format.
    
    Returns the macro_script in human-friendly YAML format.
    """
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        
        if not skill.macro_script:
            return Response(
                content="# No macro script defined for this skill\n",
                media_type="text/yaml"
            )
        
        # macro_script is already stored as YAML string
        return Response(
            content=skill.macro_script,
            media_type="text/yaml"
        )


@router.put("/skills/{skill_id}/yaml")
async def update_skill_yaml(
    skill_id: int,
    yaml_content: str = Body(..., media_type="text/yaml"),
):
    """
    Update skill macro from YAML content.
    
    Accepts raw YAML body (not JSON).
    """
    try:
        # Validate first
        is_valid, errors = validate_macro_yaml(yaml_content)
        if not is_valid:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid YAML: {'; '.join(errors)}"
            )
        
        # Store YAML directly as string
        async with session_scope() as db:
            skill = await db.get(LearnedSkill, skill_id)
            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")
            
            skill.macro_script = yaml_content
            await db.flush()
            
        # Return step count by parsing
        steps = macro_from_yaml(yaml_content)
        return {
            "success": True, 
            "message": "Skill updated from YAML",
            "step_count": len(steps)
        }
        
    except YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML parse error: {str(e)}")
    except Exception as e:
        logger.exception(f"Failed to update skill from YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update: {str(e)}")
    finally:
        await skill_discovery.reload()
