"""API routes for Atlas AppMap generation (Agent-driven source survey).

Mirrors wiki.py: the endpoint dispatches an Agent run with the AppMap Analysis
skill and read-only tools; the Agent surveys the project and calls
write_app_map, then explicitly triggers macro synthesis.
"""

import logging
import os
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUserOptional, TokenDep
from app.core.atlas.source import persistence
from app.core.atlas.source.event import publish_app_map_generate_completed
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.core.learning.discovery import skill_discovery
from app.core.project.utils import get_project_path
from app.core.tools.registry import get_tool_bundle

logger = logging.getLogger(__name__)

router = APIRouter(tags=["atlas"])

_SURVEY_TOOLS = [
    "write_app_map",
    "read_app_map",
    "list_app_maps",
    "generate_macros_from_app_map",
    "create_plan",
    "update_step_status",
]

_OUTPUT_CONTRACT = (
    "You are surveying a project's source code to produce an AppMap. "
    "Hard requirements: (1) every action must carry kind (read|write) and "
    "risk_tier (ui|data|money); (2) every action must cite controller+line and "
    "every element page+line so the validator can spot-check them against the "
    "real source — fabricated entries are rejected on write; (3) money-write "
    "fields accept absolute values only; (4) write the map via write_app_map, "
    "self-review completeness, then call generate_macros_from_app_map."
)


class AppMapGenerateRequest(BaseModel):
    project_id: int
    entity: str
    force_regenerate: bool = False


class TaskAcceptedResponse(BaseModel):
    status: str
    task_id: str


async def _ensure_app_map_analysis_skill():
    """Fetch or import the 'AppMap Analysis' learned skill."""
    await skill_discovery.ensure_system_skills_synced()
    skills = await skill_discovery.get_active_skills_list()
    for skill in skills:
        if skill.name == "AppMap Analysis":
            return await skill_discovery.get_skill_by_id(skill.id)
    return None


@router.post("/app-maps/generate", response_model=TaskAcceptedResponse)
async def generate_app_map(
    req: AppMapGenerateRequest,
    bg_tasks: BackgroundTasks,
    _token: TokenDep,
    current_user: CurrentUserOptional = None,
) -> TaskAcceptedResponse:
    path = await get_project_path(req.project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")
    if not os.path.isdir(path):
        raise HTTPException(400, f"Project path does not exist: {path}")
    if not req.entity:
        raise HTTPException(400, "entity is required")

    thread_id = f"appmap-gen-{req.project_id}-{req.entity}-{int(time.time())}"

    skill = await _ensure_app_map_analysis_skill()
    if not skill:
        logger.warning("[Atlas] AppMap Analysis skill not found; falling back to generic mission.")

    message = (
        f"**Mission Goal**: Survey the project at {path} and produce a complete "
        f"AppMap for the '{req.entity}' entity. Follow the AppMap Analysis SOP, "
        "then call write_app_map and generate_macros_from_app_map."
    )

    from app.core.context import thread_context_store

    thread_context_store.set_working_directory(thread_id, path)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=req.project_id,
        skip_message_persistence=True,
        member_id=current_user.id if current_user else None,
        metadata={"goal_prefix": "[AppMap] "},
    )
    if result.status == "failed":
        raise HTTPException(500, detail=result.error)

    read_only_file_tools = [
        t
        for t in get_tool_bundle("file_tools")
        if t not in ("edit_file", "delete_file", "move_file", "execute_command")
    ]
    ticket = ExecutionTicket(
        ticket_type="task",
        topic="AppMap Analysis",
        skill_ids=[skill.id] if skill else None,
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            system_instructions=_OUTPUT_CONTRACT,
            tools=_SURVEY_TOOLS + read_only_file_tools,
        ),
    )
    result.inputs["ticket"] = ticket.model_dump(mode="json")

    if "metadata" not in result.inputs:
        result.inputs["metadata"] = {}
    result.inputs["metadata"]["skip_persistence"] = True
    result.inputs["metadata"]["task_type"] = "app_map_generation"
    result.inputs["metadata"]["force_regenerate"] = req.force_regenerate

    bg_tasks.add_task(run_agent_background, thread_id, result.inputs)
    logger.info(
        "[AtlasAPI] Dispatched AppMap survey: project=%s entity=%s thread=%s skill_ids=%s",
        req.project_id,
        req.entity,
        thread_id,
        [skill.id] if skill else "None",
    )
    return TaskAcceptedResponse(status="accepted", task_id=thread_id)


@router.post("/app-maps/{app_map_id}/generate-macros", response_model=TaskAcceptedResponse)
async def generate_macros(
    app_map_id: int,
    _token: TokenDep,
) -> TaskAcceptedResponse:
    app_map = await persistence.get_app_map(app_map_id)
    if app_map is None:
        raise HTTPException(404, f"AppMap #{app_map_id} not found")
    if app_map.status != "active":
        raise HTTPException(400, f"AppMap #{app_map_id} is {app_map.status}")

    await publish_app_map_generate_completed(
        app_map_id=app_map_id,
        project_id=app_map.project_id,
        member_id=app_map.member_id,
    )
    return TaskAcceptedResponse(status="accepted", task_id=f"macro-synth-{app_map_id}")


@router.get("/app-maps")
async def list_app_maps(project_id: int, _token: TokenDep):
    from app.core.execution.macro import lifecycle

    maps = await persistence.list_app_maps(project_id, status=None)
    out = []
    for m in maps:
        macros = await lifecycle.list_macros(app_map_id=m.id)
        out.append(
            {
                "id": m.id,
                "project_id": m.project_id,
                "entity": m.entity,
                "platform": m.platform,
                "map_version": m.map_version,
                "status": m.status,
                "content_hash": m.content_hash,
                "actions_count": len(m.actions or []),
                "macro_count": len(macros),
                "pending_count": sum(1 for x in macros if x.status == "pending_review"),
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return out
