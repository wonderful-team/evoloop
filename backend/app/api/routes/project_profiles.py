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
from app.api.schemas.project_profiles import DiscoverRequest, DiscoverResponse, ProfileContentResponse, UpdateProfileRequest
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.state.blackboard import BlackboardState
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.domain.project.utils import get_project_path
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from app.core import file as file_utils

logger = logging.getLogger(__name__)

router = APIRouter(tags=["project-profiles"])


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
    path = await get_project_path(project_id)
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
    secrets_instruction = (
        "Please identify and record sensitive information (secrets, keys) in the document."
        if req.record_secrets else
        "DO NOT record any sensitive information"
    )
    message = (
        "**Mission Goal**: Analyze the project at {target_path}. You MUST:\n"
        "1. Identify the tech stack and project type.\n"
        "2. **Infrastructure Discovery**: Check for `docker-compose.yml`, `nginx.conf`, or database requirements. **Attempt to start/install them** (e.g., `docker-compose up -d`, `brew install`).\n"
        "3. **Deployment**: Identify all components and attempt to **start and verify** them. For PHP/Nginx projects, specifically check for correct pathinfo/proxy configuration.\n"
        "4. **Deep Verification**: Use `browser_control` to verify access and diagnose any 403/404/500 errors.\n"
        "5. **Documentation**: Generate a `PROJECT.md` at the root that summarizes the above, including an 'Infrastructure & Middleware' section. Redact secrets: {redact_secrets}.\n"
        "6. Stop and report once `PROJECT.md` is written."
    ).format(target_path=path, redact_secrets=secrets_instruction)

    # Pre-set working directory so Agent executes in the correct path
    from app.core.context import thread_context_store
    thread_context_store.set_working_directory(thread_id, path)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        goal_prefix="[Project Discovery] ",
        skip_message_persistence=True,
    )

    if result.status == "failed":
        raise HTTPException(500, detail=result.error)

    # Inject the ExecutionTicket into the initial state so SkillHydrator can load the SOP.
    blackboard = BlackboardState(
        ticket=ExecutionTicket(
            ticket_type="task",
            topic="Project Discovery",
            skill_id=skill.id if skill else None,
            agent_config=AgentRuntimeConfig(role_name="Worker"),
        )
    )
    result.inputs["blackboard"] = blackboard.model_dump(mode="json")

    # Skip persisting Agent conversation transcript to DB
    if "metadata" not in result.inputs:
        result.inputs["metadata"] = {}
    result.inputs["metadata"]["skip_persistence"] = True

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
    path = await get_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")

    file_path = os.path.join(path, "PROJECT.md")
    content = None
    if os.path.isfile(file_path):
        try:
            content = file_utils.read_file(file_path).content
        except Exception as e:
            logger.warning(f"Failed to read PROJECT.md: {e}")

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
    """Manually update the PROJECT.md content."""
    path = await get_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")

    file_path = os.path.join(path, "PROJECT.md")
    try:
        file_utils.write_file(file_path, req.content)
    except Exception as e:
        logger.error(f"Failed to write PROJECT.md: {e}")
        raise HTTPException(500, f"Failed to update profile: {e}")

    return ProfileContentResponse(
        content=req.content,
        exists=True,
    )
