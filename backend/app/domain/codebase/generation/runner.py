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
    """Dispatch an AppMap Agent — the SKILL.md handles the full pipeline."""
    path = await get_project_path(project_id)
    if not path or not os.path.isdir(path):
        raise FileNotFoundError(f"Project path not found: {path}")

    thread_id = f"appmap-gen-{project_id}-{int(time.time())}"
    from app.core.context import thread_context_store
    thread_context_store.set_working_directory(thread_id, path)

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
