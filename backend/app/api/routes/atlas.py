"""API routes for Atlas AppMap generation (Agent-driven source survey).

Mirrors wiki.py: the endpoint dispatches an Agent run with the AppMap Analysis
skill and read-only tools; the Agent surveys the project and calls
write_app_map, then explicitly triggers macro synthesis.
"""

import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUserOptional, TokenDep
from app.core.atlas.source import persistence
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import DispatchStatus, dispatch_agent_run
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.core.learning.macro import list_macros
from app.core.learning.skills.discovery import skill_discovery
from app.core.project.utils import get_project_path
from app.core.tools.registry import get_tool_bundle
from app.utils.id import unique_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["atlas"])

_SURVEY_TOOLS = [
    "write_app_map",
    "read_app_map",
    "list_app_maps",
    "create_plan",
    "update_step_status",
]

_OUTPUT_CONTRACT = (
    "You are surveying a project's source code to produce an AppMap. "
    "Hard requirements: (1) every action must carry kind (read|write) and "
    "risk_tier (ui|data|money); (2) every action must cite controller+line and "
    "every element page+line so the validator can spot-check them against the "
    "real source — fabricated entries are rejected on write; (3) money-write "
    "fields accept absolute values only; (4) write the map via write_app_map "
    "and self-review completeness."
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

    thread_id = unique_id("appmap-gen", req.project_id, req.entity)

    skill = await _ensure_app_map_analysis_skill()
    if not skill:
        logger.warning("[Atlas] AppMap Analysis skill not found; falling back to generic mission.")

    message = (
        f"**Mission Goal**: Survey the project at {path} and produce a complete "
        f"AppMap for the '{req.entity}' entity. Follow the AppMap Analysis SOP, "
        "then call write_app_map."
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
    if result.status == DispatchStatus.FAILED:
        raise HTTPException(500, detail=result.error)

    read_only_file_tools = [
        t for t in get_tool_bundle("file_tools")
        if t not in ("edit_file", "delete_file", "move_file", "execute_command")
    ]
    result.inputs["ticket"] = ExecutionTicket(
        ticket_type="task",
        topic="AppMap Analysis",
        skill_ids=[skill.id] if skill else None,
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            system_instructions=_OUTPUT_CONTRACT,
            tools=_SURVEY_TOOLS + read_only_file_tools,
        ),
    )

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


@router.get("/app-maps")
async def list_app_maps(project_id: int, _token: TokenDep):

    maps = await persistence.list_app_maps(project_id, status=None)
    out = []
    for m in maps:
        macros = await list_macros(app_map_id=m.id)
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


class OperationMapTrainRequest(BaseModel):
    project_id: int
    entity: str | None = None
    base_url: str | None = None
    skip_static_seed: bool = False


@router.post("/operation-maps/train", response_model=TaskAcceptedResponse)
async def train_operation_maps(
    req: OperationMapTrainRequest,
    bg_tasks: BackgroundTasks,
    _token: TokenDep,
) -> TaskAcceptedResponse:
    """Train a project's operation library (AppMap seed).

    Dispatched as a background task: indexing -> AppMap (deterministic pipeline).
    """
    from app.core.atlas.source.train_orchestrator import train_project

    path = await get_project_path(req.project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")

    task_id = unique_id("operation-train", req.project_id)
    bg_tasks.add_task(
        train_project,
        project_id=req.project_id,
        entity=req.entity,
        skip_static_seed=req.skip_static_seed,
    )
    logger.info(
        "[AtlasAPI] Dispatched operation-map training: project=%s entity=%s task=%s",
        req.project_id,
        req.entity,
        task_id,
    )
    return TaskAcceptedResponse(status="accepted", task_id=task_id)


@router.get("/operation-maps/status")
async def operation_map_status(
    project_id: int,
    _token: TokenDep,
) -> dict:
    """Summarize the project's verified operation library.

    Per-entity verified/pending macro counts plus runtime element repair
    markers (runtime_fixed / runtime_absent), showing training completeness.
    """

    maps = await persistence.list_app_maps(project_id, status="active")
    entities = []
    for m in maps:
        macros = await list_macros(app_map_id=m.id)
        entities.append(
            {
                "entity": m.entity,
                "platform": m.platform,
                "map_version": m.map_version,
                "verified_macros": sum(1 for x in macros if x.status == "verified"),
                "pending_macros": sum(1 for x in macros if x.status == "pending_review"),
                "elements_runtime_fixed": sum(
                    1 for el in (m.elements or []) if el.get("runtime_fixed")
                ),
                "elements_runtime_absent": sum(
                    1 for el in (m.elements or []) if el.get("runtime_absent")
                ),
            }
        )
    return {"project_id": project_id, "entities": entities}
