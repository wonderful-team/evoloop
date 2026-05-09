"""
API routes for Wiki.

Read operations are direct DB queries.
Generation is Agent-driven via the Skill system (Wiki Generation SKILL.md),
following the same pattern as project_profile discovery.
"""
import logging
import os
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import TokenDep, require_benefit
from app.domain.wiki.schemas import WikiGenerationRequest, WikiGenerationResponse, WikiPageRead
from app.domain.wiki.service import wiki_service
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.state.blackboard import BlackboardState
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.core.evocloud import evocloud_manager
from app.i18n.service import i18n
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


async def _resolve_project_path(project_id: int) -> str:
    """Resolve local project path from project_id."""
    try:
        project = await evocloud_manager.get_project_by_id(project_id)
        if project and project.path and os.path.isdir(project.path):
            return project.path
    except Exception as e:
        logger.debug(f"[Wiki] Cloud lookup failed for {project_id}: {e}")

    try:
        from sqlalchemy import select
        from app.infrastructure.database.sql.database import AsyncSessionLocal
        from app.models import Repository

        async with AsyncSessionLocal() as session:
            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repo = result.scalar_one_or_none()
            if repo and repo.local_path and os.path.isdir(repo.local_path):
                return repo.local_path
    except Exception as e:
        logger.debug(f"[Wiki] DB lookup failed for {project_id}: {e}")

    return ""


async def _ensure_wiki_generation_skill():
    """Fetch or import the 'Wiki Generation' learned skill."""
    from app.infrastructure.database.sql.database import session_scope
    from app.models.learning import LearnedSkill

    async with session_scope() as session:
        from sqlalchemy import select
        stmt = select(LearnedSkill).where(
            LearnedSkill.name == "Wiki Generation",
            LearnedSkill.is_active == True,
        )
        result = await session.execute(stmt)
        skill = result.scalar_one_or_none()
        if skill:
            return skill

    try:
        from app.core.config import settings
        from app.core.learning.skill_importer import SkillImporter

        import_path = os.path.join(settings.SKILLS_DIR, "roles", "wiki_generation")
        if os.path.isdir(import_path):
            await SkillImporter.import_from_directory(settings.SKILLS_DIR)

        async with session_scope() as session:
            from sqlalchemy import select
            stmt = select(LearnedSkill).where(
                LearnedSkill.name == "Wiki Generation",
                LearnedSkill.is_active == True,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"[Wiki] Failed to import Wiki Generation skill: {e}")
        return None


@router.get("/{project_id}", response_model=list[WikiPageRead])
async def get_wiki_pages(project_id: int, _token: TokenDep):
    """Get all wiki pages for a project."""
    return wiki_service.get_pages(project_id)


@router.post("/generate", dependencies=[Depends(require_benefit("wiki_generation"))])
async def generate_wiki(
    req: WikiGenerationRequest,
    bg_tasks: BackgroundTasks,
    _token: TokenDep,
) -> WikiGenerationResponse:
    """
    Trigger Wiki generation via Agent + Skill system.
    The Agent follows the Wiki Generation SKILL.md SOP to autonomously
    survey the project, plan the structure, and write pages via tools.
    """
    path = await _resolve_project_path(req.project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")
    if not os.path.isdir(path):
        raise HTTPException(400, f"Project path does not exist: {path}")

    thread_id = f"wiki-gen-{req.project_id}-{int(time.time())}"

    skill = await _ensure_wiki_generation_skill()
    if not skill:
        logger.warning("[Wiki] Wiki Generation skill not found; falling back to generic mission.")

    if req.force_regenerate:
        from sqlmodel import delete
        from app.infrastructure.database.resource_manager import db_resource_manager as rm
        from app.models.wiki import WikiPage
        with Session(rm.sync_engine) as session:
            session.exec(delete(WikiPage).where(WikiPage.project_id == req.project_id))
            session.commit()
        logger.info(f"[Wiki] Cleared existing wiki pages for project {req.project_id}")

    user_lang = SystemConfigService.get_language_preference()

    # Inject language and TOC requirements into system_instructions so the
    # Agent treats them as hard constraints rather than soft suggestions.
    system_instructions = (
        f"You are a technical documentation expert. "
        f"ALL wiki content, page titles, and the table of contents MUST be written in {user_lang}. "
        f"After writing all content pages, you MUST create a dedicated 'Table of Contents' page "
        f"(title='目录' if Chinese, else 'Table of Contents') with slug='toc' and order=0. "
        f"The TOC page must list all wiki pages in a hierarchical tree format."
    )

    message = (
        f"**Mission Goal**: Generate a comprehensive Wiki documentation for the project at {path}.\n"
        "You MUST:\n"
        "1. Survey the project structure (list_directory, read README and key config files).\n"
        "2. Plan a logical Wiki structure (Overview, Architecture, Setup, API, etc.).\n"
        "3. Generate content page by page using write_wiki_page tool.\n"
        "4. Include Mermaid diagrams, code blocks, and tables where appropriate.\n"
        "5. Extract key concepts and store them in Memory.\n"
        "6. CRITICAL: Create a 'Table of Contents' page (slug='toc', order=0) listing all pages in a tree hierarchy. Do NOT skip this step.\n"
        "7. Stop and report once the Wiki is complete.\n"
        f"Topic: {req.topic}"
    )

    from app.core.context import thread_context_store
    thread_context_store.set_working_directory(thread_id, path)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=req.project_id,
        goal_prefix="[Wiki Generation] ",
        skip_message_persistence=True,
    )

    if result.status == "failed":
        raise HTTPException(500, detail=result.error)

    blackboard = BlackboardState(
        ticket=ExecutionTicket(
            ticket_type="task",
            topic="Wiki Generation",
            skill_id=skill.id if skill else None,
            agent_config=AgentRuntimeConfig(
                role_name="Worker",
                system_instructions=system_instructions,
                tools=["write_wiki_page", "read_wiki_page", "list_wiki_pages"],
            ),
        )
    )
    result.inputs["blackboard"] = blackboard.model_dump(mode="json")

    # Skip persisting Agent conversation transcript to DB for this background batch task
    if "metadata" not in result.inputs:
        result.inputs["metadata"] = {}
    result.inputs["metadata"]["skip_persistence"] = True

    from fastapi import BackgroundTasks
    # BackgroundTasks is injected by FastAPI; we need to use it properly
    # But here we're in the route function. We can't use bg_tasks without injecting it.
    # Let's use asyncio.create_task instead, or inject BackgroundTasks.
    # Actually, let's look at project_profiles.py — it uses bg_tasks.add_task.
    # We should do the same.

    async def _run_wiki_with_toc(thread_id: str, inputs: dict, project_id: int, lang: str):
        """Wrapper that runs the agent and ensures TOC exists afterward."""
        await run_agent_background(thread_id, inputs)
        wiki_service.ensure_toc_page(project_id, lang)

    bg_tasks.add_task(_run_wiki_with_toc, thread_id, result.inputs, req.project_id, user_lang)

    logger.info(
        f"[WikiAPI] Dispatched wiki generation mission for project {req.project_id} "
        f"(thread_id={thread_id}, skill_id={skill.id if skill else 'None'}, lang={user_lang})"
    )

    return WikiGenerationResponse(
        status="accepted",
        message=i18n.get("wiki.generation_queued"),
        task_id=thread_id,
    )
