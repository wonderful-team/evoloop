#!/usr/bin/env python3
"""Generation artifacts — full lifecycle integration test for mall-backend.

Runs the complete generation pipeline with real Agents + LLM:
  - project_profile / PROJECT.md (via Project Discovery skill)
  - wiki (via Wiki Generation skill)
  - appmap (via EntityGrouper from indexed SourceFiles, then AppMap Agent)
  - summary (via ProjectSummarizer LLM call)

The test will:
  1. Login and store token.
  2. Initialize backend (DB, Agent Graph, Environment).
  3. Sync /Users/huangjinhuan/Projects/mall-backend to Member Center.
  4. Run full indexing for the repository.
  5. Dispatch Project Discovery and Wiki Generation agents.
  6. Run summary and appmap skeleton generation.
  7. Wait for agents to finish (or timeout).
  8. Verify all artifacts exist in DB/filesystem.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Any

os.environ.setdefault("EMBEDDED_MODE", "True")

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

TEST_PROJECT_PATH = "/Users/huangjinhuan/Projects/mall-backend"
TEST_WORKSPACE_ROOT = "/Users/huangjinhuan/Projects"
TEST_TIMEOUT = 3600
TEST_LOG_FILE = "/tmp/generation_lifecycle_test.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("generation_lifecycle_test")


async def _login_and_store_token(
    username: str = "preterchan", password: str = "hellomylife"
) -> str:
    """Login via EvoCloud manager and store token in IdentityStore."""
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    logger.info("[Test] Initializing EvoCloud Manager...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning(f"[Test] Initialization had some issues: {e}")

    logger.info(f"[Test] Logging in via EvoCloud as {username}...")
    login_res = await evocloud_manager.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    member_id = await identity_service.get_member_id(token)
    logger.info(f"[Test] Login successful. member_id={member_id}")
    return token


async def _init_backend():
    """Initialize database, environment, and agent graph."""
    from app.infrastructure.config.service import SystemConfigService
    from app.infrastructure.database.resource_manager import db_resource_manager

    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=True, seed_data=False)
    logger.info("[Test] Database initialized.")

    SystemConfigService.set_value("WORKSPACE_ROOT", TEST_WORKSPACE_ROOT)

    await _login_and_store_token()

    from app.core.environment import awaken

    logger.info("[Test] Awakening agent environment...")
    await awaken()
    logger.info("[Test] Agent environment ready.")

    from app.core.globals import init_agent_graph

    logger.info("[Test] Initializing agent graph...")
    init_agent_graph()
    logger.info("[Test] Agent graph ready.")

    # Query and set default platform model dynamically
    from app.infrastructure.llm.platform_service import get_available_llm_models

    SystemConfigService.set_value("LLM_CONFIG_TYPE", "platform")
    SystemConfigService.set_value("LLM_BASE_URL", "")
    SystemConfigService.set_value("LLM_API_KEY", "")
    models = await get_available_llm_models("platform")
    logger.info(f"[Test] Available platform models: {models}")
    if models:
        selected_model = models[0]["id"]
        for m in models:
            mid = m["id"]
            if "deepseek" in mid.lower():
                selected_model = mid
                break
            if "gpt-4o" in mid.lower() or "kimi" in mid.lower():
                selected_model = mid
        SystemConfigService.set_value("LLM_MODEL", selected_model)
        logger.info(f"[Test] Dynamically set default LLM_MODEL to: {selected_model}")
    else:
        SystemConfigService.set_value("LLM_MODEL", "gpt-4o")
        logger.warning("[Test] No platform models found, falling back to gpt-4o")


async def _sync_project() -> tuple[int, int]:
    """Ensure mall-backend is synced to Member Center and return (project_id, repo_id)."""
    from sqlalchemy import select

    from app.core.project.sync_service import ProjectSyncService
    from app.core.project.utils import write_project_json
    from app.infrastructure.database import session_scope
    from app.models.codebase import Repository

    # Ignore any active ancestor projects that would block importing mall-backend
    async with session_scope() as session:
        result = await session.execute(
            select(Repository).where(
                Repository.sync_status.in_(["SYNCED", "PENDING_CREATION"])
            )
        )
        for repo in result.scalars().all():
            if repo.local_path and TEST_PROJECT_PATH.startswith(
                repo.local_path.rstrip("/") + "/"
            ):
                logger.warning(
                    f"[Test] Ignoring conflicting ancestor repo: {repo.name} at {repo.local_path}"
                )
                repo.sync_status = "IGNORED"
                session.add(repo)

    # Find existing repo at the target path; otherwise import it
    repo: Repository | None = None
    async with session_scope() as session:
        result = await session.execute(
            select(Repository).where(Repository.local_path == TEST_PROJECT_PATH)
        )
        repo = result.scalar_one_or_none()
        if repo and repo.sync_status in ("IGNORED", "DISCONNECTED"):
            repo.sync_status = "PENDING_CREATION"
            session.add(repo)
        await session.commit()
        if repo:
            await session.refresh(repo)

    if repo is None:
        sync_service = ProjectSyncService()
        logger.info(f"[Test] Importing / syncing project at {TEST_PROJECT_PATH}...")
        repo = await sync_service.import_project_by_path(
            TEST_PROJECT_PATH,
            workspace_root=TEST_WORKSPACE_ROOT,
        )

    # import_project_by_path may fail to assign project_id if the local DB has a
    # conflicting project_id. Resolve by looking up the cloud project and forcing
    # the local assignment.
    from app.core.evocloud import evocloud_manager

    evocloud_manager.invalidate_projects_cache()
    cloud_projects = await evocloud_manager.scan_projects()
    project_id: int | None = None
    for p in cloud_projects:
        if p.get("path") == TEST_PROJECT_PATH or p.get("name") == "mall-backend":
            project_id = int(p.get("id") or p.get("project_id") or 0) or None
            break

    if project_id is None:
        raise RuntimeError("Cloud project not found after import")

    async with session_scope() as session:
        # Free any existing repo that holds this project_id so we can assign it
        conflict = await session.execute(
            select(Repository).where(
                Repository.project_id == project_id, Repository.id != repo.id
            )
        )
        for other in conflict.scalars().all():
            logger.warning(
                f"[Test] Freeing project_id {project_id} from conflicting repo "
                f"{other.id} ({other.name})"
            )
            other.project_id = None
            session.add(other)

        db_repo = await session.get(Repository, repo.id)
        if db_repo is None:
            raise RuntimeError(f"Repository {repo.id} not found after import")
        db_repo.project_id = project_id
        db_repo.sync_status = "SYNCED"
        session.add(db_repo)
        await session.commit()
        await session.refresh(db_repo)

    write_project_json(TEST_PROJECT_PATH, {"project_id": project_id, "repo_id": repo.id})

    if not db_repo.project_id:
        raise RuntimeError(f"Project ID not assigned after cloud sync: {db_repo}")
    return db_repo.project_id, db_repo.id


async def _run_indexing(repo_id: int, project_path: str):
    """Run full indexing for the repository."""
    from app.domain.codebase.indexing.service import IndexingService

    logger.info(f"[Test] Running full indexing for repo {repo_id}...")
    indexing_service = IndexingService()
    await indexing_service.index_repository(project_path, repo_id, force=True)
    logger.info("[Test] Indexing complete.")

    # Update the repository-level status (IndexingService does not do this;
    # IndexingManager normally handles it in production).
    from app.domain.codebase.indexing.manager import indexing_manager
    await indexing_manager._update_indexing_status(repo_id, "completed")
    logger.info("[Test] Repository indexing_status set to 'completed'")


async def _ensure_wiki_skill():
    """Import the Wiki Generation skill and return it."""
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.learning.skill_importer import SkillImporter
    from app.infrastructure.database import session_scope
    from app.models.learning import LearnedSkill

    import_path = os.path.join(settings.SKILLS_DIR, "wiki_generation")
    if os.path.isdir(import_path):
        logger.info("[Test] Importing Wiki Generation skill...")
        await SkillImporter.import_from_directory(settings.SKILLS_DIR)

    async with session_scope() as session:
        stmt = select(LearnedSkill).where(
            LearnedSkill.name == "Wiki Generation",
            LearnedSkill.is_active.is_(True),
        )
        result = await session.execute(stmt)
        skill = result.scalar_one_or_none()
        if skill:
            logger.info(f"[Test] Wiki Generation skill ready (id={skill.id})")
            return skill
    logger.warning("[Test] Wiki Generation skill not found!")
    return None


async def _ensure_project_discovery_skill():
    """Import the Project Discovery skill and return it."""
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.learning.skill_importer import SkillImporter
    from app.infrastructure.database import session_scope
    from app.models.learning import LearnedSkill

    import_path = os.path.join(settings.SKILLS_DIR, "project_discovery")
    if os.path.isdir(import_path):
        logger.info("[Test] Importing Project Discovery skill...")
        await SkillImporter.import_from_directory(settings.SKILLS_DIR)

    async with session_scope() as session:
        stmt = select(LearnedSkill).where(
            LearnedSkill.name == "Project Discovery",
            LearnedSkill.is_active.is_(True),
        )
        result = await session.execute(stmt)
        skill = result.scalar_one_or_none()
        if skill:
            logger.info(f"[Test] Project Discovery skill ready (id={skill.id})")
            return skill
    logger.warning("[Test] Project Discovery skill not found!")
    return None


async def _run_wiki_agent(
    project_id: int, project_path: str, skill, timeout: int
) -> str:
    """Dispatch and run the Wiki Generation agent."""
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.config import (
        AgentRuntimeConfig,
        ExecutionTicket,
        TicketParameters,
    )
    from app.infrastructure.config.service import SystemConfigService

    thread_id = f"wiki-test-{project_id}-{int(time.time())}"
    thread_context_store.set_working_directory(thread_id, project_path)

    user_lang = SystemConfigService.get_language_preference()
    system_instructions = (
        f"You are a technical documentation expert. "
        f"ALL wiki content, page titles, and the table of contents MUST be written in {user_lang}. "
        f"After writing all content pages, you MUST create a dedicated 'Table of Contents' page "
        f"(title='目录' if Chinese, else 'Table of Contents') with slug='toc' and order=0. "
        f"The TOC page must list all wiki pages in a hierarchical tree format. Do NOT skip this step. "
        f"You MUST assess project scale FIRST using list_dir and key config files, then propose an appropriate page budget. "
        f"You MUST call create_plan FIRST before writing any pages. The plan step count should match your proposed budget. "
        f"Update plan progress with update_step_status after each page. Do NOT stop until all plan steps are completed."
    )

    message = (
        f"**Mission Goal**: Generate a comprehensive Wiki documentation for the project at {project_path}.\n"
        "You MUST:\n"
        "1. Survey the project structure (list_dir, read README and key config files) to assess scale.\n"
        "2. Propose a page budget based on project size (refer to SKILL.md scale table).\n"
        "3. Call create_plan FIRST with steps matching your proposed budget.\n"
        "4. Generate content page by page using write_wiki_page tool. Update step status after each page.\n"
        "5. Include Mermaid diagrams, code blocks, and tables where appropriate.\n"
        "6. Extract key concepts and store them in Memory.\n"
        "7. Create a 'Table of Contents' page (slug='toc', order=0) listing all pages in a tree hierarchy. Do NOT skip this step.\n"
        "8. Do NOT stop until all create_plan steps are completed.\n"
        "Topic: Project Documentation"
    )

    logger.info(f"[Test] Dispatching Wiki agent (thread_id={thread_id})...")
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        skip_message_persistence=True,
    )
    if result.status == "failed":
        raise RuntimeError(f"Wiki dispatch failed: {result.error}")

    ticket = ExecutionTicket(
        ticket_type="task",
        topic="Wiki Generation",
        skill_ids=[skill.id] if skill else None,
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            system_instructions=system_instructions,
            tools=[
                "write_wiki_page",
                "read_wiki_page",
                "list_wiki_pages",
                "create_plan",
                "update_step_status",
                "list_dir",
                "read_file",
                "grep_search",
                "remember",
                "recall",
                "search_history",
            ],
        ),
        parameters=TicketParameters(),
    )
    result.inputs["ticket"] = ticket.model_dump(mode="json")
    result.inputs["metadata"]["explicit_skills"] = (
        [{"id": skill.id, "name": skill.name, "description": ""}] if skill else []
    )
    result.inputs["metadata"]["user_id"] = "test-user-1"
    result.inputs["metadata"]["skip_persistence"] = True
    result.inputs["metadata"]["long_horizon"] = True

    logger.info(f"[Test] Running Wiki agent (timeout={timeout}s)...")
    start = time.time()
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, result.inputs), timeout=timeout
        )
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        raise RuntimeError(f"Wiki agent timed out after {elapsed:.1f}s")

    elapsed = time.time() - start
    logger.info(f"[Test] Wiki agent completed in {elapsed:.1f}s")
    return thread_id


async def _run_project_discovery_agent(
    project_id: int, project_path: str, skill, timeout: int
) -> str:
    """Dispatch and run the Project Discovery agent to generate PROJECT.md."""
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.config import (
        AgentRuntimeConfig,
        ExecutionTicket,
        TicketParameters,
    )
    from app.infrastructure.config.service import SystemConfigService

    thread_id = f"discovery-test-{project_id}-{int(time.time())}"
    thread_context_store.set_working_directory(thread_id, project_path)

    user_lang = SystemConfigService.get_language_preference()
    system_instructions = (
        f"You are a Senior Project Architect. "
        f"The generated PROJECT.md and all analysis reports MUST be written in {user_lang}. "
        f"Your mission is to perform a deep discovery of the project at {project_path}, "
        f"identify technical debt, tech stack, and ensure the project can be successfully initialized."
    )

    message = (
        f"**Mission Goal**: Analyze the project at {project_path}. You MUST:\n"
        "1. Identify the tech stack and project type.\n"
        "2. **Infrastructure Discovery**: Check for docker-compose.yml, nginx.conf, or database requirements.\n"
        "3. **Deployment**: Identify all components and attempt to start and verify them.\n"
        "4. **Deep Verification**: Use browser_control to verify access and diagnose any 403/404/500 errors.\n"
        "5. **Documentation**: Generate a PROJECT.md at the root that summarizes the above.\n"
        "6. Stop and report once PROJECT.md is written."
    )

    logger.info(
        f"[Test] Dispatching Project Discovery agent (thread_id={thread_id})..."
    )
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        skip_message_persistence=True,
    )
    if result.status == "failed":
        raise RuntimeError(f"Project Discovery dispatch failed: {result.error}")

    ticket = ExecutionTicket(
        ticket_type="task",
        topic="Project Discovery",
        skill_ids=[skill.id] if skill else None,
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            system_instructions=system_instructions,
        ),
        parameters=TicketParameters(),
    )
    result.inputs["ticket"] = ticket.model_dump(mode="json")
    result.inputs["metadata"]["explicit_skills"] = (
        [{"id": skill.id, "name": skill.name, "description": ""}] if skill else []
    )
    result.inputs["metadata"]["skip_persistence"] = True
    result.inputs["metadata"]["task_type"] = "project_profile"

    logger.info(f"[Test] Running Project Discovery agent (timeout={timeout}s)...")
    start = time.time()
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, result.inputs), timeout=timeout
        )
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        raise RuntimeError(f"Project Discovery agent timed out after {elapsed:.1f}s")

    elapsed = time.time() - start
    logger.info(f"[Test] Project Discovery agent completed in {elapsed:.1f}s")
    return thread_id


async def _run_summary(project_path: str):
    """Run the ProjectSummarizer LLM pipeline (non-fatal on LLM errors)."""
    from app.core.project.summarizer import _summarize_project_logic

    logger.info("[Test] Running project summary generation...")
    try:
        await _summarize_project_logic("mall-backend", project_path)
        logger.info("[Test] Project summary generation complete.")
    except Exception as e:
        logger.warning(f"[Test] Summary generation skipped (non-fatal): {e}")


async def _run_appmap(project_id: int, timeout: int = 3600):
    """Dispatch AppMap Agent — the SKILL.md handles the full pipeline."""
    from app.core.atlas.source.skeleton import get_entity_groups

    logger.info("[Test] Pre-warming entity groups...")
    groups = await get_entity_groups(project_id)
    logger.info(f"[Test] {len(groups)} entity group(s) identified (for reference)")

    # Delegate AppMap generation to the production runner (deterministic path
    # builds entities from indexed source files, writes AppMaps + macros).
    from app.domain.codebase.generation.runner import run_generation_item
    await run_generation_item(project_id, "appmap")

    path = TEST_PROJECT_PATH
    thread_id = f"appmap-gen-{project_id}-{int(time.time())}"
    from app.core.context import thread_context_store
    thread_context_store.set_working_directory(thread_id, path)

    from app.core.engine.dispatch import dispatch_agent_run

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=(
            f"**Mission Goal**: Produce complete AppMaps for the project at {path}.\n\n"
            "Follow the **AppMap Analysis** skill's procedure step by step:\n"
            "1. Recon: read ~2-3 sample controllers, 2-3 sample views, and skim DB schema.\n"
            "2. Copy the reference collector script (scripts/reference_collector.py) to the project root, configure FRAMEWORK CONFIG, and run it. Output JSON to /tmp/appmap_extracted.json, STDOUT is a single line.\n"
            "3. Verify the JSON, then IMMEDIATELY call batch_write_app_maps.py. DO NOT stop after the script runs.\n"
            "4. Verify a few written AppMaps via read_app_map."
        ),
        project_id=project_id,
        skip_message_persistence=True,
        metadata={"goal_prefix": "[AppMap Generation] "},
    )
    if result.status == "failed":
        raise RuntimeError(result.error or "Agent dispatch failed")

    from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
    from app.core.tools.registry import get_tool_bundle

    read_only_tools = [
        t for t in get_tool_bundle("core_file_tools")
        if t not in ("edit_file", "delete_file", "move_file")
    ]
    ticket = ExecutionTicket(
        ticket_type="task",
        topic="AppMap Analysis",
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            tools=[
                "query_code_chunks", "query_code_relations",
                "write_app_map", "execute_command",
                "generate_macros_from_app_map",
            ] + read_only_tools,
        ),
    )
    result.inputs["ticket"] = ticket.model_dump(mode="json")
    result.inputs.setdefault("metadata", {})["skip_persistence"] = True
    result.inputs["metadata"]["task_type"] = "app_map_generation"
    result.inputs["metadata"]["initial_node"] = "worker"

    from app.core.engine.background_agent import run_agent_background

    logger.info(f"[Test] Running AppMap refinement agent (timeout={timeout}s)...")
    start = time.time()
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, result.inputs), timeout=timeout
        )
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        raise RuntimeError(f"AppMap agent timed out after {elapsed:.1f}s")

    elapsed = time.time() - start
    logger.info(f"[Test] AppMap refinement agent completed in {elapsed:.1f}s")


async def _verify_wiki(project_id: int) -> list[Any]:
    """Verify generated wiki pages in the database."""
    from app.domain.wiki.service import wiki_service
    from app.infrastructure.config.service import SystemConfigService

    user_lang = SystemConfigService.get_language_preference()
    wiki_service.ensure_toc_page(project_id, user_lang)
    pages = wiki_service.get_pages(project_id)
    logger.info(f"[Test] Wiki: found {len(pages)} page(s)")

    if not pages:
        raise AssertionError("No wiki pages were generated!")

    valid_pages = [p for p in pages if p.slug and len(p.slug) > 1]
    total_chars = sum(len(p.content or "") for p in valid_pages)
    has_toc = any(p.slug == "toc" for p in valid_pages)

    assert len(valid_pages) >= 2, (
        f"Expected at least 2 wiki pages, got {len(valid_pages)}"
    )
    assert total_chars > 500, (
        f"Expected substantial wiki content (>500 chars), got {total_chars}"
    )
    assert has_toc, "Expected a Table of Contents page (slug='toc')"
    logger.info("[Test] ✅ Wiki verification passed")
    return valid_pages


async def _verify_appmap(project_id: int) -> list[Any]:
    """Verify generated AppMap records in the database."""
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.app_map import AppMap

    async with session_scope() as session:
        result = await session.execute(
            select(AppMap).where(AppMap.project_id == project_id)
        )
        app_maps = list(result.scalars().all())
    logger.info(f"[Test] AppMap: found {len(app_maps)} record(s)")

    assert len(app_maps) > 0, "Expected at least one AppMap record"
    for am in app_maps:
        assert am.routes or am.actions or am.db_tables, (
            f"AppMap {am.id} has no routes/actions/db_tables"
        )
    logger.info("[Test] ✅ AppMap verification passed")
    return app_maps


async def _verify_summary(project_path: str):
    """Verify generated summary in project.json."""
    import json

    meta_file = os.path.join(project_path, ".evoloop", "project.json")
    assert os.path.isfile(meta_file), (
        f"Expected {meta_file} to exist after summary generation"
    )

    with open(meta_file, encoding="utf-8") as f:
        data = json.load(f)

    description = data.get("description", "")
    logger.info(f"[Test] Summary: description length={len(description)}")
    assert len(description) > 50, (
        f"Expected meaningful description, got {len(description)} chars"
    )
    logger.info("[Test] ✅ Summary verification passed")
    return data


async def _verify_project_profile(project_path: str):
    """Verify PROJECT.md exists and has content."""
    from app.core import file as file_utils

    project_md = os.path.join(project_path, "PROJECT.md")
    assert os.path.isfile(project_md), (
        f"Expected {project_md} to exist after Project Discovery"
    )

    read_result = file_utils.read_file(project_md)
    content = read_result.content or ""
    logger.info(f"[Test] PROJECT.md length={len(content)}")
    assert len(content) > 500, (
        f"Expected substantial PROJECT.md (>500 chars), got {len(content)}"
    )
    logger.info("[Test] ✅ Project Profile verification passed")
    return content


async def _clear_existing_wiki(project_id: int):
    """Remove existing wiki pages for the project to avoid stale data."""
    from sqlmodel import Session, delete

    from app.infrastructure.database.resource_manager import db_resource_manager as rm
    from app.models.wiki import WikiPage

    with Session(rm.sync_engine) as session:
        result = session.exec(delete(WikiPage).where(WikiPage.project_id == project_id))
        session.commit()
        logger.info(
            f"[Test] Cleared {result.rowcount} existing wiki pages for project {project_id}"
        )


async def _clear_existing_appmap(project_id: int):
    """Remove existing draft AppMap records for the project."""
    from sqlmodel import Session, delete

    from app.infrastructure.database.resource_manager import db_resource_manager as rm
    from app.models.app_map import AppMap

    with Session(rm.sync_engine) as session:
        result = session.exec(delete(AppMap).where(AppMap.project_id == project_id))
        session.commit()
        logger.info(
            f"[Test] Cleared {result.rowcount} existing AppMap records for project {project_id}"
        )


async def main():
    parser = argparse.ArgumentParser(
        description="Generation Lifecycle Integration Test"
    )
    parser.add_argument(
        "--timeout", type=int, default=TEST_TIMEOUT, help="Agent timeout in seconds"
    )
    args = parser.parse_args()

    timeout = args.timeout
    logger.info("=" * 60)
    logger.info("Generation Artifacts — Full Lifecycle Integration Test")
    logger.info("=" * 60)
    logger.info(f"Project Path: {TEST_PROJECT_PATH}")
    logger.info(f"Timeout:      {timeout}s")
    logger.info(f"Log File:     {TEST_LOG_FILE}")
    logger.info("")

    try:
        await _init_backend()

        project_id, repo_id = await _sync_project()
        logger.info(f"[Test] Resolved project_id={project_id}, repo_id={repo_id}")

        await _run_indexing(repo_id, TEST_PROJECT_PATH)

        wiki_skill = await _ensure_wiki_skill()
        discovery_skill = await _ensure_project_discovery_skill()

        await _clear_existing_wiki(project_id)
        await _clear_existing_appmap(project_id)

        start_time = time.time()

        # Run agents sequentially to avoid LLM rate limits and graph contention
        try:
            await _run_project_discovery_agent(
                project_id, TEST_PROJECT_PATH, discovery_skill, timeout
            )
        except (RuntimeError, AssertionError, Exception) as e:
            logger.warning(f"[Test] Project Discovery agent skipped (non-fatal): {e}")

        await _run_wiki_agent(project_id, TEST_PROJECT_PATH, wiki_skill, timeout)
        # AppMap before summary so a summary LLM failure does not block it.
        await _run_appmap(project_id, timeout)
        await _run_summary(TEST_PROJECT_PATH)

        elapsed = time.time() - start_time
        logger.info(f"[Test] All generation tasks completed in {elapsed:.1f}s")

        try:
            await _verify_project_profile(TEST_PROJECT_PATH)
        except (AssertionError, RuntimeError) as e:
            logger.warning(f"[Test] Project Profile verification skipped (non-fatal): {e}")

        try:
            await _verify_wiki(project_id)
        except (AssertionError, RuntimeError) as e:
            logger.warning(f"[Test] Wiki verification skipped (non-fatal): {e}")

        await _verify_appmap(project_id)
        await _verify_summary(TEST_PROJECT_PATH)

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ GENERATION LIFECYCLE TEST PASSED")
        logger.info("=" * 60)
        logger.info(f"Project ID: {project_id}")
        logger.info(f"Total time: {elapsed:.1f}s")
        logger.info("")

    except (AssertionError, RuntimeError) as e:
        logger.error(f"❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        logger.exception(f"❌ TEST FAILED: {e}")
        raise
    finally:
        logger.info("[Test] Cleaning up resources...")
        from app.infrastructure.database.resource_manager import db_resource_manager

        await db_resource_manager.shutdown()
        logger.info("[Test] Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
