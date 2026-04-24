"""
Project Memory Context Provider

Subscribes to memory.context_gather events and injects project-level
context (README, structure, norms) into memory extraction without
creating circular core->domain dependencies.
"""

import asyncio
import logging
import os

from app.constants import PROJECT_NORM_FILES
from app.core.config import settings
from app.core.events.decorators import event_register, event_subscribe
from app.infrastructure.config import SystemConfigService
from app.core.memory.events import (
    MEMORY_CONTEXT_GATHER_EVENT_TYPE,
    MemoryContextGatherEvent,
)
from app.utils import render_template

logger = logging.getLogger(__name__)


@event_register()
class ProjectMemoryContextProvider:
    """
    Provides project context (README, structure, norms) for memory extraction.

    Automatically registered via @event_register and discovered at startup.
    Renders its own markdown fragment via Jinja2 template — memory layer
    only sees the final formatted string.
    """

    @event_subscribe(MEMORY_CONTEXT_GATHER_EVENT_TYPE)
    async def on_context_gather(self, event: MemoryContextGatherEvent) -> None:
        """Render project context fragment and append to event data."""
        project_id = event.data.project_id
        if not project_id:
            return

        project_path = SystemConfigService.get_value("WORKSPACE_ROOT")
        if not project_path:
            logger.debug("[ProjectContextProvider] WORKSPACE_ROOT not set, skipping.")
            return

        try:
            context = await self._build_template_context(project_path)
            if context:
                fragment = render_template(
                    "domain/project/memory_context.j2",
                    **context,
                )
                if fragment.strip():
                    event.data.context_fragments.append(fragment.strip())
        except Exception as e:
            logger.warning(f"[ProjectContextProvider] Failed to render context: {e}")

    async def _build_template_context(self, project_path: str) -> dict | None:
        """Gather raw data and return a dict for the Jinja2 template."""
        from app.domain.project.service import project_context_manager

        readme = ""
        structure = ""

        try:
            loop = asyncio.get_event_loop()
            readme = await loop.run_in_executor(
                None,
                project_context_manager.extract_description_from_readme,
                project_path,
            )
            readme = readme[:1000] if readme else ""
        except Exception as e:
            logger.debug(f"[ProjectContextProvider] README extraction failed: {e}")

        try:
            structure = await project_context_manager.get_project_structure(project_path)
        except Exception as e:
            logger.debug(f"[ProjectContextProvider] Structure extraction failed: {e}")

        norms = []
        try:
            loop = asyncio.get_event_loop()
            norms = await loop.run_in_executor(
                None, self._scan_norm_files_sync, project_path
            )
        except Exception as e:
            logger.debug(f"[ProjectContextProvider] Norms scan failed: {e}")

        if not readme and not structure and not norms:
            return None

        return {
            "readme_summary": readme,
            "project_structure": structure,
            "norms": [{"file": n[0], "content": n[1]} for n in norms] if norms else [],
        }

    def _scan_norm_files_sync(self, project_path: str) -> list[tuple[str, str]]:
        """Synchronous norm file scanner (runs in thread pool).

        Returns list of (filename, first_500_chars) tuples.
        """
        norms = []
        for norm_file in PROJECT_NORM_FILES:
            path = os.path.join(project_path, norm_file)
            if os.path.exists(path) and os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read(500)
                        norms.append((norm_file, content))
                except Exception:
                    continue
        return norms
