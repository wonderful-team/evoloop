"""
API routes for project profile discovery.

Discovery is Agent-driven via the Skill system:
1. The API looks up (or imports) the "Project Discovery" learned skill.
2. It constructs an ExecutionTicket with ``skill_id`` set so the SkillHydrator
   automatically injects the SOP into the Worker's system prompt.
3. A concise mission message is dispatched; the Skill SOP (not the API) dictates
   the analysis and write-file steps.
"""
import logging
import os
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.deps import TokenDepOptional
from app.api.schemas.project_profiles import DiscoverRequest, DiscoverResponse, ProfileContentResponse
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.state.blackboard import BlackboardState
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.core.evocloud import evocloud_manager
from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from app.utils import file as file_utils

logger = logging.getLogger(__name__)

router = APIRouter(tags=["project-profiles"])

# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _resolve_project_path(project_id: int) -> str:
    """
    Resolve local project path from project_id.

    Resolution order:
    1. Cloud API (evocloud_manager.get_project_by_id) → project.path
    2. Local DB (Repository table) → repo.local_path
    """
    # 1. Try Cloud API
    try:
        project = await evocloud_manager.get_project_by_id(project_id)
        if project and project.path and os.path.isdir(project.path):
            return project.path
    except Exception as e:
        logger.debug(f"[ProjectProfiles] Cloud lookup failed for {project_id}: {e}")

    # 2. Try local DB
    try:
        from sqlalchemy import select
        from app.infrastructure.database.sql.database import AsyncSessionLocal
        from app.models.codebase import Repository

        async with AsyncSessionLocal() as session:
            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repo = result.scalar_one_or_none()
            if repo and repo.local_path and os.path.isdir(repo.local_path):
                return repo.local_path
    except Exception as e:
        logger.debug(f"[ProjectProfiles] DB lookup failed for {project_id}: {e}")

    return ""

# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

async def _ensure_project_discovery_skill() -> LearnedSkill | None:
    """Fetch or import the 'Project Discovery' learned skill."""
    # 1. Try DB lookup by exact name
    async with session_scope() as session:
        from sqlalchemy import select
        stmt = select(LearnedSkill).where(
            LearnedSkill.name == "Project Discovery",
            LearnedSkill.is_active == True,
        )
        result = await session.execute(stmt)
        skill = result.scalar_one_or_none()
        if skill:
            return skill

    # 2. Not found — trigger import from built-in skills directory
    try:
        from app.core.config import settings
        from app.core.learning.skill_importer import SkillImporter

        import_path = os.path.join(settings.SKILLS_DIR, "roles", "project_discovery")
        if os.path.isdir(import_path):
            await SkillImporter.import_from_directory(settings.SKILLS_DIR)

        # Re-query after import
        async with session_scope() as session:
            from sqlalchemy import select
            stmt = select(LearnedSkill).where(
                LearnedSkill.name == "Project Discovery",
                LearnedSkill.is_active == True,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"[ProjectProfiles] Failed to import Project Discovery skill: {e}")
        return None

@router.post("/{project_id}/profile/discover", response_model=DiscoverResponse)
async def discover_profile(
    project_id: int,
    req: DiscoverRequest,
    bg_tasks: BackgroundTasks,
    _token: TokenDepOptional = None,
):
    """
    Trigger Agent-driven project discovery via the Skill system.

    The API resolves the skill, builds an ExecutionTicket with ``skill_id``,
    and lets the Skill SOP guide the Worker. No template-level step-by-step
    instructions are needed — the SKILL.md owns the execution flow.
    """
    path = await _resolve_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")
    if not os.path.isdir(path):
        raise HTTPException(400, f"Project path does not exist: {path}")

    thread_id = f"discovery-{project_id}-{int(time.time())}"

    # Resolve the skill (lazy import if missing)
    skill = await _ensure_project_discovery_skill()
    if not skill:
        logger.warning("[ProjectProfiles] Project Discovery skill not found; falling back to generic mission.")

    # Concise mission — the Skill SOP (injected into Worker system prompt) owns the detailed flow
    message = "Create a comprehensive PROJECT.md at the project root to document this codebase for AI assistants."

    # Pre-set working directory so Agent executes in the correct path
    from app.core.context import thread_context_store
    thread_context_store.set_working_directory(thread_id, path)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        goal_prefix="[Project Discovery] ",
    )

    if result.status == "failed":
        raise HTTPException(500, detail=result.error)

    # Inject the ExecutionTicket into the initial state so SkillHydrator can load the SOP.
    # API layer only specifies the skill — tool authorization is Supervisor's decision.
    blackboard = BlackboardState(
        ticket=ExecutionTicket(
            ticket_type="task",
            topic="Project Discovery",
            skill_id=skill.id if skill else None,
            agent_config=AgentRuntimeConfig(role_name="Worker"),
        )
    )
    result.inputs["blackboard"] = blackboard.model_dump(mode="json")

    bg_tasks.add_task(run_agent_background, thread_id, result.inputs)

    logger.info(
        f"[ProjectProfilesAPI] Dispatched discovery mission for project {project_id} "
        f"(thread_id={thread_id}, skill_id={skill.id if skill else 'None'})"
    )

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
    """Get the current PROJECT.md content for a project."""
    path = await _resolve_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")

    file_path = os.path.join(path, "PROJECT.md")
    content = None
    if os.path.isfile(file_path):
        try:
            content = file_utils.read_file(file_path)
        except Exception as e:
            logger.warning(f"Failed to read PROJECT.md: {e}")

    return ProfileContentResponse(
        content=content,
        exists=content is not None,
    )