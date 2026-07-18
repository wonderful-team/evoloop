"""Background generation runner — bridges GenerationScheduler status to real execution."""

from __future__ import annotations

import logging
import os
import time

from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.core.project.utils import get_project_path
from app.core.tools.registry import get_tool_bundle
from app.domain.codebase.generation.scheduler import (
    mark_generation_completed,
    mark_generation_failed,
)

logger = logging.getLogger(__name__)


async def run_generation_item(project_id: int, item: str) -> None:
    """Execute a single generation artifact in the background.

    Designed to be used as a ``BackgroundTasks`` target from the API layer.
    """
    try:
        if item == "wiki":
            await _run_wiki(project_id)
        elif item == "appmap":
            await _run_appmap(project_id)
        elif item == "summary":
            await _run_summary(project_id)
        else:
            await mark_generation_failed(project_id, item, f"Unknown item: {item}")
            return
        await mark_generation_completed(project_id, item)
    except Exception as exc:
        logger.exception("[GenerationRunner] %s failed for project %s", item, project_id)
        await mark_generation_failed(project_id, item, str(exc))


async def _run_wiki(project_id: int) -> None:
    """Spawn a Wiki Agent that reads from the DB index and writes wiki pages."""
    path = await get_project_path(project_id)
    if not path or not os.path.isdir(path):
        raise FileNotFoundError(f"Project path not found: {path}")

    thread_id = f"wiki-gen-{project_id}-{int(time.time())}"
    from app.core.context import thread_context_store
    thread_context_store.set_working_directory(thread_id, path)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=(
            f"**Mission Goal**: Generate a comprehensive Wiki documentation "
            f"for the project at {path}.\n\n"
            "Use `query_code_chunks(is_api_route=true)` to discover API routes, "
            "and `query_source_files(scan_status='completed')` for the file list. "
            "Write pages via `write_wiki_page`."
        ),
        project_id=project_id,
        skip_message_persistence=True,
        metadata={"goal_prefix": "[Wiki Generation] "},
    )
    if result.status == "failed":
        raise RuntimeError(result.error or "Agent dispatch failed")

    read_only_tools = [
        t for t in get_tool_bundle("core_file_tools")
        if t not in ("edit_file", "delete_file", "move_file", "execute_command")
    ]
    ticket = ExecutionTicket(
        ticket_type="task",
        topic="Wiki Generation",
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            tools=[
                "query_code_chunks", "query_code_relations", "query_source_files",
                "write_wiki_page", "edit_wiki_page", "read_wiki_page", "list_wiki_pages",
                "create_plan", "update_step_status",
            ] + read_only_tools,
        ),
    )
    result.inputs["ticket"] = ticket.model_dump(mode="json")
    result.inputs.setdefault("metadata", {})["skip_persistence"] = True
    result.inputs["metadata"]["task_type"] = "wiki_generation"
    await run_agent_background(thread_id, result.inputs)


async def _run_appmap(project_id: int) -> None:
    """Run deterministic AppMap extraction + batch write, then dispatch an
    AppMap Agent for verification."""
    path = await get_project_path(project_id)
    if not path or not os.path.isdir(path):
        raise FileNotFoundError(f"Project path not found: {path}")

    from app.core.atlas.source.skeleton import get_entity_groups

    groups = await get_entity_groups(project_id)
    if not groups:
        logger.info("[AppMap] No entity groups found for project %s", project_id)
        return

    # Deterministic path: run collector + batch writer directly.
    # The Agent is only for verification — not for data production.
    ref_script = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        "../../core/atlas/source/skeleton/collector.py",
    ))
    batch_script = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        "../../core/atlas/source/skeleton/batch_writer.py",
    ))

    import subprocess
    logger.info("[AppMap] Running collector...")
    subprocess.run(
        ["uv", "run", "python", ref_script, path],
        capture_output=True, timeout=120,
    )
    logger.info("[AppMap] Running batch writer...")
    subprocess.run(
        ["uv", "run", "python", batch_script,
         "--project-id", str(project_id), "--input", "/tmp/appmap_extracted.json"],
        capture_output=True, timeout=300,
    )

    thread_id = f"appmap-gen-{project_id}-{int(time.time())}"
    from app.core.context import thread_context_store
    thread_context_store.set_working_directory(thread_id, path)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=(
            f"**Mission Goal**: Verify and refine the generated AppMaps for the project at {path}.\n\n"
            "The AppMap extraction has already been completed by the deterministic pipeline.\n"
            "1. List a few written AppMaps via `read_app_map` to verify quality.\n"
            "2. If you see gaps (missing elements, routes, or db_tables), fix the collector script "
            "at collect_appmaps.py and re-run it, then call batch_write_app_maps.py.\n"
            "3. Report coverage summary."
        ),
        project_id=project_id,
        skip_message_persistence=True,
        metadata={"goal_prefix": "[AppMap Generation] "},
    )
    if result.status == "failed":
        raise RuntimeError(result.error or "Agent dispatch failed")

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
                "read_app_map",
                "write_app_map", "execute_command",
                "generate_macros_from_app_map",
            ] + read_only_tools,
        ),
    )
    result.inputs["ticket"] = ticket.model_dump(mode="json")
    result.inputs.setdefault("metadata", {})["skip_persistence"] = True
    result.inputs["metadata"]["task_type"] = "app_map_generation"
    await run_agent_background(thread_id, result.inputs)


async def _run_summary(project_id: int) -> None:
    """Generate a one-page project summary from the DB index."""
    from app.core.project.summarizer import summarize_project_task

    path = await get_project_path(project_id)
    if not path or not os.path.isdir(path):
        raise FileNotFoundError(f"Project path not found: {path}")
    project_name = os.path.basename(path)

    summarize_project_task(project_name, path)

    meta_file = os.path.join(path, ".evoloop", "project.json")
    if os.path.exists(meta_file):
        with open(meta_file) as f:
            content = f.read()
    else:
        content = None
        logger.warning(f"[_run_summary] project.json not found at {meta_file}")

    await mark_generation_completed(project_id, "summary", content=content)
