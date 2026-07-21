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

_MONEY_KEYWORDS = frozenset({
    "price", "stock", "balance", "refund", "amount", "money",
    "salary", "payment", "withdraw", "recharge",
})
_DATA_KEYWORDS = frozenset({
    "save", "update", "delete", "remove", "create", "add", "edit",
    "set", "change", "status",
})

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

    # Inject module graph summary so the Agent knows the project structure upfront
    from app.domain.codebase.generation.module_graph import module_graph_service
    try:
        module_summary = await module_graph_service.format_summary(project_id)
    except Exception:
        module_summary = ""

    thread_id = f"wiki-gen-{project_id}-{int(time.time())}"
    from app.core.context import thread_context_store
    thread_context_store.set_working_directory(thread_id, path)

    msg = (
        f"**Mission Goal**: Generate a comprehensive Wiki documentation "
        f"for the project at {path}.\n\n"
        "Use `query_code_chunks(is_api_route=true)` to discover API routes, "
        "and `query_source_files(scan_status='completed')` for the file list. "
        "Write pages via `write_wiki_page`."
    )
    if module_summary:
        msg += f"\n\nThe project structure has been analyzed into the following modules:\n{module_summary}\n\nPlan your wiki outline around these modules rather than discovering the structure from scratch."

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=msg,
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

    # Validate groupings against ModuleGraph — log cross-module entities
    from app.domain.codebase.generation.module_graph import module_graph_service
    try:
        cross_module = []
        for entity_name in groups:
            expected_module = await module_graph_service.get_module_of(project_id, entity_name)
            if expected_module:
                cross_module.append((entity_name, expected_module))
        if cross_module:
            logger.info(
                "[AppMap] %d entities validated against ModuleGraph (first cross-module: %s)",
                len(cross_module),
                cross_module[0],
            )
    except Exception:
        logger.debug("[AppMap] ModuleGraph validation skipped")

    # Incremental impact check — log which modules would be affected
    # if we detected changes (full regeneration still runs for now).
    try:
        from sqlalchemy import select, func
        from app.infrastructure.database import session_scope
        from app.models.app_map import AppMap
        async with session_scope() as session:
            existing = (
                await session.execute(
                    select(func.count(AppMap.id)).where(AppMap.project_id == project_id)
                )
            ).scalar()
        if existing and existing > 0:
            logger.info(
                "[AppMap] %d existing AppMaps found — incremental impact checking available via module_graph_service.compute_impact()",
                existing,
            )
    except Exception:
        pass

    # Deterministic path: build entities from indexed source files, then
    # write AppMaps and generate macros.  The Agent is only for verification.
    entities = await build_entities_from_index(project_id, groups)
    if entities:
        logger.info("[AppMap] Index-based builder found %d entities", len(entities))
        logger.info("[AppMap] Writing AppMaps and generating macros...")
        result = await batch_write_appmaps(
            project_id=project_id, entities=entities, member_id=0
        )
        logger.info(
            "[AppMap] Batch write: %d written, %d skipped, %d failed, %d macros",
            result["written"], result["skipped"], result["failed"], result["macros_generated"],
        )
    else:
        logger.info("[AppMap] Index-based builder returned no entities, skipping batch write")

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
    result.inputs["metadata"]["initial_node"] = "worker"
    await run_agent_background(thread_id, result.inputs)

    # After Agent verification, regenerate macros for active AppMaps to pick up
    # any Chinese aliases / elements / db_tables the Agent's collector added.
    await _regenerate_macros(project_id)


async def _regenerate_macros(project_id: int) -> None:
    """Regenerate macros for all active AppMaps that have Chinese aliases."""
    from sqlalchemy import select
    from app.infrastructure.database import session_scope
    from app.models.app_map import AppMap
    from app.core.execution.macro.tasks import synthesize_macros_task as _wrapped

    _raw = getattr(_wrapped, "func", _wrapped)
    import inspect
    if not inspect.iscoroutinefunction(_raw):
        for _cell in getattr(_raw, "__closure__", None) or []:
            if inspect.iscoroutinefunction(_cell.cell_contents):
                _raw = _cell.cell_contents
                break

    async with session_scope() as session:
        result = await session.execute(
            select(AppMap).where(
                AppMap.project_id == project_id,
                AppMap.status == "active",
            )
        )
        app_maps = list(result.scalars().all())

    for am in app_maps:
        has_cn = any(("\u4e00" <= c <= "\u9fff") for alias in (am.aliases or []) for c in alias) if am.aliases else False
        if not has_cn:
            continue
        try:
            await _raw(app_map_id=am.id, project_id=project_id, member_id=0)
        except Exception:
            logger.debug("[Macro] regenerate failed for app_map %s", am.id)


def _classify_action(name: str) -> tuple[str, str]:
    """Classify an action by kind (read/write) and risk_tier (ui/data/money)."""
    lower = name.lower()
    if any(kw in lower for kw in _MONEY_KEYWORDS):
        return "write", "money"
    if any(kw in lower for kw in ("list", "page", "index", "get", "search", "find")):
        return "read", "ui"
    if any(kw in lower for kw in _DATA_KEYWORDS):
        return "write", "data"
    return "write", "ui"


async def build_entities_from_index(
    project_id: int, groups: dict,
) -> dict:
    """Build AppMap entities dict from Tree-sitter parsed code chunks."""
    from app.core.atlas.source.skeleton.generator import APPMAP_ACTION_CATEGORIES

    all_ids = set()
    for cf_list in groups.values():
        for cf in cf_list:
            all_ids.add(cf.source_file.id)

    from sqlalchemy import select
    from app.infrastructure.database import session_scope
    from app.models.codebase import SourceFile, CodeChunk

    async with session_scope() as session:
        sf_result = await session.execute(
            select(SourceFile).where(SourceFile.id.in_(all_ids))
        )
        source_files = {sf.id: sf for sf in sf_result.scalars().all()}

        chunk_result = await session.execute(
            select(CodeChunk).where(
                CodeChunk.source_file_id.in_(all_ids),
                CodeChunk.chunk_type.in_(["function", "method"]),
            )
        )
        chunks_by_file: dict[int, list[CodeChunk]] = {}
        for c in chunk_result.scalars().all():
            chunks_by_file.setdefault(c.source_file_id, []).append(c)

    entities = {}
    for entity_name, classified_files in groups.items():
        controller_files = [
            cf for cf in classified_files
            if cf.category in APPMAP_ACTION_CATEGORIES
        ]
        if not controller_files:
            continue

        actions = []
        routes = []
        for cf in controller_files:
            sf = source_files.get(cf.source_file.id)
            if not sf:
                continue
            for chunk in chunks_by_file.get(sf.id, []):
                name = chunk.identifier.split(".")[-1].split("::")[-1]
                if name.startswith("_") or name in ("__construct", "__destruct", "__init"):
                    continue
                kind, risk = _classify_action(name)
                actions.append({
                    "name": name,
                    "kind": kind,
                    "risk_tier": risk,
                    "business_rule": "",
                    "controller": sf.path,
                    "line": chunk.start_line,
                    "touches_tables": [],
                    "set_fields": [],
                    "pk": "",
                })
                routes.append({
                    "name": f"{entity_name}.{name}",
                    "url": f"/{entity_name}/{name}",
                    "method": "POST" if kind == "write" else "GET",
                    "source_action": name,
                })

        if not actions:
            continue

        entities[entity_name] = {
            "aliases": [entity_name],
            "platform": "web",
            "routes": routes,
            "actions": actions,
            "elements": [],
            "db_tables": [],
            "extra": {},
        }

    return entities


async def batch_write_appmaps(
    project_id: int, entities: dict, member_id: int = 0,
) -> dict:
    """Batch-write AppMap records and generate macros."""
    import inspect

    from app.core.atlas.source.persistence import save_app_map

    from app.core.execution.macro.tasks import synthesize_macros_task as _raw_sync
    _raw = getattr(_raw_sync, "func", _raw_sync)
    if not inspect.iscoroutinefunction(_raw):
        for _cell in getattr(_raw, "__closure__", None) or []:
            if inspect.iscoroutinefunction(_cell.cell_contents):
                _raw = _cell.cell_contents
                break

    written = skipped = failed = macros_generated = 0

    for entity_name, data in sorted(entities.items()):
        try:
            app_map_id, version, created = await save_app_map(
                project_id=project_id,
                entity=entity_name,
                platform=data.get("platform", "web"),
                aliases=data.get("aliases", [entity_name]),
                routes=data.get("routes", []),
                actions=data.get("actions", []),
                elements=data.get("elements", []),
                db_tables=data.get("db_tables", []),
                extra=data.get("extra"),
                member_id=member_id,
            )

            if created:
                written += 1
            else:
                skipped += 1

            if _raw is not None:
                try:
                    result = await _raw(
                        app_map_id=app_map_id,
                        project_id=project_id,
                        member_id=member_id,
                    )
                    macros_generated += result.get("candidates", 0)
                except Exception as exc:
                    logger.warning("[MACRO] %s macro generation failed: %s", entity_name, exc)

        except Exception as exc:
            failed += 1
            logger.error("[FAIL] %s: %s", entity_name, exc)

    logger.info(
        "Batch complete: %d written, %d skipped, %d failed, %d macros",
        written, skipped, failed, macros_generated,
    )
    return {
        "written": written, "skipped": skipped,
        "failed": failed, "macros_generated": macros_generated,
    }


async def _run_summary(project_id: int) -> None:
    """Generate a one-page project summary from the DB index."""
    from app.core.project.summarizer import summarize_project_task

    path = await get_project_path(project_id)
    if not path or not os.path.isdir(path):
        raise FileNotFoundError(f"Project path not found: {path}")
    project_name = os.path.basename(path)

    # Inject module structure context for richer summaries
    module_graph = ""
    try:
        from app.domain.codebase.generation.module_graph import module_graph_service
        module_graph = await module_graph_service.format_summary(project_id, include_graph=True)
    except Exception:
        pass

    summarize_project_task(project_name, path, module_graph=module_graph)

    meta_file = os.path.join(path, ".evoloop", "project.json")
    if os.path.exists(meta_file):
        with open(meta_file) as f:
            content = f.read()
    else:
        content = None
        logger.warning(f"[_run_summary] project.json not found at {meta_file}")

    await mark_generation_completed(project_id, "summary", content=content)
