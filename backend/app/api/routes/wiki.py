"""
API routes for Wiki.

Read operations are direct DB queries.
Generation is Agent-driven via the Skill system (Wiki Generation SKILL.md),
following the same pattern as project_profile discovery.
"""

import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import delete
from sqlmodel import Session

from app.api.deps import CurrentUserOptional, TokenDep, require_benefit
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.core.project.utils import get_project_path
from app.core.tools.registry import get_tool_bundle
from app.domain.wiki.schemas import (
    WikiGenerationRequest,
    WikiGenerationResponse,
    WikiPageRead,
)
from app.domain.wiki.service import wiki_service
from app.i18n.service import i18n
from app.infrastructure.config.service import SystemConfigService
from app.utils.id import unique_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


async def _ensure_wiki_generation_skill():
    """Fetch the 'Wiki Generation' learned skill from the repository."""
    from app.core.learning.skills.repository import skill_repository

    return await skill_repository.get_by_name("Wiki Generation", visible_only=True)


@router.get("/{project_id}", response_model=list[WikiPageRead])
async def get_wiki_pages(
    project_id: int,
    _token: TokenDep,
    current_user: CurrentUserOptional = None,
):
    """Get all wiki pages for a project."""
    return wiki_service.get_pages(project_id, member_id=current_user.id if current_user else None)


@router.post("/generate", dependencies=[Depends(require_benefit("wiki_generation"))])
async def generate_wiki(
    req: WikiGenerationRequest,
    bg_tasks: BackgroundTasks,
    _token: TokenDep,
    current_user: CurrentUserOptional = None,
) -> WikiGenerationResponse:
    """
    Trigger Wiki generation via Agent + Skill system.
    The Agent follows the Wiki Generation SKILL.md SOP to autonomously
    survey the project, plan the structure, and write pages via tools.
    """
    path = await get_project_path(req.project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")
    if not os.path.isdir(path):
        raise HTTPException(400, f"Project path does not exist: {path}")

    thread_id = unique_id("wiki-gen", req.project_id)

    skill = await _ensure_wiki_generation_skill()
    if not skill:
        logger.warning("[Wiki] Wiki Generation skill not found; falling back to generic mission.")

    if req.force_regenerate:
        from app.infrastructure.database.resource_manager import (
            db_resource_manager as rm,
        )
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
        f"ALL wiki content and page titles MUST be written in {user_lang}. "
        "You must build a hierarchical documentation tree. "
        "Always create parent pages before child pages, and link them using the parent_title parameter. "
        "You do NOT need to specify slugs or file paths — use page titles as addresses."
    )

    message = (
        f"**Mission Goal**: Generate a comprehensive, hierarchical Wiki documentation for the project at {path}.\n"
        "You MUST:\n"
        "0. If `.evoloop/project.json` contains a `framework_profile` field, "
        "read it first via read_file to understand module boundaries and domain vocabulary "
        "before querying the code index.\n"
        "1. Survey the project structure (list_dir, read README and key config files).\n"
        "2. Plan a logical tree-like structure (Overview -> Architecture, Setup, API, etc.).\n"
        "3. Generate content page by page using write_wiki_page(title, content, parent_title=...). \n"
        "   IMPORTANT: Create parent pages BEFORE child pages to ensure correct linking.\n"
        "4. For incremental fixes to existing pages, use edit_wiki_page(title, old_string, new_string).\n"
        "5. Include Mermaid diagrams, code blocks, and tables where appropriate.\n"
        "6. Stop and report once the Wiki structure is complete.\n"
        f"Topic: {req.topic}"
    )

    from app.core.context import thread_context_store

    thread_context_store.set_working_directory(thread_id, path)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=req.project_id,
        skip_message_persistence=True,
        member_id=current_user.id if current_user else None,
        metadata={"goal_prefix": "[Wiki Generation] "},
    )

    if result.status == "failed":
        raise HTTPException(500, detail=result.error)

    result.inputs["ticket"] = ExecutionTicket(
        ticket_type="task",
        topic="Wiki Generation",
        skill_ids=[skill.id] if skill else None,
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            system_instructions=system_instructions,
            tools=[
                "write_wiki_page",
                "edit_wiki_page",
                "read_wiki_page",
                "list_wiki_pages",
                "create_plan",
                "update_step_status",
            ] + [
                t for t in get_tool_bundle("file_tools")
                if t not in ("edit_file", "delete_file", "move_file", "execute_command")
            ],
        ),
    )

    # Skip persisting Agent conversation transcript to DB for this background batch task
    if "metadata" not in result.inputs:
        result.inputs["metadata"] = {}
    result.inputs["metadata"]["skip_persistence"] = True
    result.inputs["metadata"]["task_type"] = "wiki_generation"

    bg_tasks.add_task(run_agent_background, thread_id, result.inputs)

    logger.info(
        f"[WikiAPI] Dispatched wiki generation mission for project {req.project_id} "
        f"(thread_id={thread_id}, skill_ids={[skill.id] if skill else 'None'}, lang={user_lang})"
    )

    return WikiGenerationResponse(
        status="accepted",
        message=i18n.get("wiki.generation_queued"),
        task_id=thread_id,
    )
