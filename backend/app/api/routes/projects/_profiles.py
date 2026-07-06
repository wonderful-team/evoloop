"""
API routes for project profile discovery.

Discovery is Agent-driven via the Skill system.
"""

import logging
import os
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.deps import TokenDep, TokenDepOptional, require_benefit
from app.api.schemas.projects._profiles import (
    DiscoverRequest,
    DiscoverResponse,
    ProfileContentResponse,
    UpdateProfileRequest,
)
from app.core import file as file_utils
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.core.project.utils import get_project_path
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)

router = APIRouter(tags=["project-profiles"])


async def _ensure_project_discovery_skill() -> LearnedSkill | None:
    async with session_scope() as session:
        from sqlalchemy import select
        stmt = select(LearnedSkill).where(
            LearnedSkill.name == "Project Discovery",
            LearnedSkill.is_active,
        )
        result = await session.execute(stmt)
        skill = result.scalar_one_or_none()
        if skill:
            return skill

    try:
        async with session_scope() as session:
            from sqlalchemy import select
            stmt = select(LearnedSkill).where(
                LearnedSkill.name == "Project Discovery",
                LearnedSkill.is_active,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning("[ProjectProfiles] Failed to import Project Discovery skill: %s", e)
        return None


@router.post("/{project_id}/profile/discover", response_model=DiscoverResponse, dependencies=[Depends(require_benefit("project_profile"))])
async def discover_profile(
    project_id: int,
    req: DiscoverRequest,
    bg_tasks: BackgroundTasks,
    _token: TokenDep,
):
    path = await get_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")
    if not os.path.isdir(path):
        raise HTTPException(400, f"Project path does not exist: {path}")

    thread_id = f"discovery-{project_id}-{int(time.time())}"

    skill = await _ensure_project_discovery_skill()
    if not skill:
        logger.warning("[ProjectProfiles] Project Discovery skill not found; falling back to generic mission.")

    secrets_instruction = (
        "Please identify and record sensitive information (secrets, keys) in the document."
        if req.record_secrets else
        "DO NOT record any sensitive information"
    )
    message = (
        f"**Mission Goal**: Analyze the project at {path}. You MUST:\n"
        "1. Identify the tech stack and project type.\n"
        "2. **Infrastructure Discovery**: Check for `docker-compose.yml`, `nginx.conf`, or database requirements. **Attempt to start/install them** (e.g., `docker-compose up -d`, `brew install`).\n"
        "3. **Deployment**: Identify all components and attempt to **start and verify** them. For PHP/Nginx projects, specifically check for correct pathinfo/proxy configuration.\n"
        "4. **Deep Verification**: Use `browser_control` to verify access and diagnose any 403/404/500 errors.\n"
        f"5. **Documentation**: Generate a `PROJECT.md` at the root that summarizes the above, including an 'Infrastructure & Middleware' section. Redact secrets: {secrets_instruction}.\n"
        "6. Stop and report once `PROJECT.md` is written."
    )

    from app.core.context import thread_context_store
    thread_context_store.set_working_directory(thread_id, path)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        skip_message_persistence=True,
        metadata={"goal_prefix": "[Project Discovery] "},
    )

    if result.status == "failed":
        raise HTTPException(500, detail=result.error)

    user_lang = SystemConfigService.get_language_preference()

    system_instructions = (
        f"You are a Senior Project Architect. "
        f"The generated PROJECT.md and all analysis reports MUST be written in {user_lang}. "
        f"Your mission is to perform a deep discovery of the project at {path}, "
        f"identify technical debt, tech stack, and ensure the project can be successfully initialized."
    )

    ticket = ExecutionTicket(
        ticket_type="task",
        topic="Project Discovery",
        skill_ids=[skill.id] if skill else None,
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            system_instructions=system_instructions,
        ),
    )
    result.inputs["ticket"] = ticket.model_dump(mode="json")

    if "metadata" not in result.inputs:
        result.inputs["metadata"] = {}
    result.inputs["metadata"]["skip_persistence"] = True
    result.inputs["metadata"]["task_type"] = "project_profile"

    bg_tasks.add_task(run_agent_background, thread_id, result.inputs)

    logger.info("[ProjectProfilesAPI] Dispatched discovery mission for project %d (thread_id=%s, skill_ids=%s)",
                project_id, thread_id, [skill.id] if skill else "None")

    return DiscoverResponse(
        status="queued",
        project_id=project_id,
        thread_id=thread_id,
    )


@router.get("/{project_id}/profile", response_model=ProfileContentResponse)
async def get_profile(
    project_id: int,
    _token: TokenDepOptional = None,
):
    path = await get_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")

    file_path = os.path.join(path, "PROJECT.md")
    content = None
    if os.path.isfile(file_path):
        try:
            content = file_utils.read_file(file_path).content
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning("Failed to read PROJECT.md: %s", e)

    return ProfileContentResponse(
        content=content,
        exists=content is not None,
    )


@router.patch("/{project_id}/profile", response_model=ProfileContentResponse)
async def update_profile(
    project_id: int,
    req: UpdateProfileRequest,
    _token: TokenDepOptional = None,
):
    path = await get_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")

    file_path = os.path.join(path, "PROJECT.md")
    try:
        file_utils.write_file(file_path, req.content)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("Failed to write PROJECT.md: %s", e)
        raise HTTPException(500, f"Failed to update profile: {e}")

    return ProfileContentResponse(
        content=req.content,
        exists=True,
    )
