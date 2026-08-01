"""
query_concepts — Concept knowledge query tool.

Semantic search over project-level and global concepts that agents
have saved via save_concepts. Read-side counterpart of save_concepts.
"""

import logging
from typing import Annotated

from app.constants import DEFAULT_PROJECT_ID
from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

logger = logging.getLogger(__name__)


async def _search_concepts(
    query: str | None,
    project_id: int | None = None,
    limit: int = 5,
) -> list[dict]:
    from app.core.memory.lifespan import MemoryLifespanManager
    try:
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        concepts = await container.memory_manager.search_concepts(
            query or "", project_id=project_id, limit=limit,
        )
        source = "global" if project_id == DEFAULT_PROJECT_ID else "project"
        return [
            {"name": c.name, "description": c.description, "source": source}
            for c in concepts
        ]
    except Exception as e:
        logger.warning(f"[query_concepts] Search failed: {e}")
        return []


@evoloop_tool(
    summary_template="Querying project concepts: {query}",
)
async def query_concepts(
    query: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Search project-level and global concepts saved by agents.

    Use this when you need to find previously saved technical concepts,
    architecture decisions, or patterns for the current project. This is
    the read-side counterpart of save_concepts.

    For project files (PROJECT.md, source code), use the file tools directly.
    For wiki pages, use list_wiki_pages / read_wiki_page.
    """
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    project_id = ctx.project_id if ctx else 0

    if not project_id or project_id == DEFAULT_PROJECT_ID:
        return "Global mode: no project knowledge available. Switch to a project first."

    concepts = await _search_concepts(query if query else None, project_id=project_id, limit=5)
    global_concepts = await _search_concepts(query if query else None, project_id=DEFAULT_PROJECT_ID, limit=3)

    sections = []

    if concepts:
        lines = [f"- **{c['name']}**: {c['description']}" for c in concepts]
        sections.append(f"## Project Concepts ({len(concepts)})\n" + "\n".join(lines))

    if global_concepts:
        lines = [f"- **{c['name']}**: {c['description']}" for c in global_concepts]
        sections.append(f"## Global Concepts (cross-project, {len(global_concepts)})\n" + "\n".join(lines))

    if not sections:
        return f"No concept knowledge found for project {project_id}."

    return f"# Project Knowledge (project_id={project_id})\n\n" + "\n\n".join(sections)
