import asyncio
import json
import logging
import os

from app.constants import DEFAULT_PROJECT_ID
from app.core import file as file_utils
from app.core.evocloud import evocloud_manager
from app.core.monitoring.activity import activity_monitor
from app.core.project.service import project_context_manager
from app.infrastructure.queue.factory import get_scheduler, shared_task
from app.utils.async_utils import flush_loop_bound_resources
from app.utils.json import dumps

logger = logging.getLogger(__name__)


# --- Helper Logic for Summarization (Async) ---
async def _summarize_project_logic(name: str, path: str):
    """
    Core logic to summarize a project using LLM.
    Functionally equivalent to the old _summarize_project method.
    """
    logger.info(f"[ProjectSummarizer] Analyzing {name}...")

    # 0. Resolve Project ID Early (Used for Graph Lookup)
    project_id = DEFAULT_PROJECT_ID  # Default (global mode)
    try:
        projects = await evocloud_manager.scan_projects()
        abs_path = os.path.abspath(path)
        matched = None
        for p in projects:
            if p.get("path") and os.path.abspath(p.get("path")) == abs_path:
                matched = p
                break
        if not matched:
            for p in projects:
                if p.get("name") == name:
                    matched = p
                    break
        if matched:
            project_id = matched.get("id")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Early project ID resolution failed: {e}")

    # Start Activity
    sys_tid = f"sys:{project_id}:summarization"
    await activity_monitor.start_run(sys_tid, f"Summarize Project: {name}")
    await activity_monitor.update_agent_state(sys_tid, "Summarizing", "Project Analysis", "Gathering Context...")

    container = None
    try:
        arch_summary = "Not available yet."
        from app.domain.codebase.indexing.directory_summarizer import (
            DirectorySummarizer,
        )
        try:
            summary_dir = await DirectorySummarizer.get_summary(path)
            if summary_dir:
                arch_summary = summary_dir
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"[ProjectSummarizer] Failed to fetch directory summary: {e}")

        # Update Status
        await activity_monitor.update_agent_state(sys_tid, "Summarizing", "Project Analysis", "Reading Files & Context...")

        # 1. Gather Context (Files)
        from app.core.file import FileTraverser
        files = []
        try:
            for entry in FileTraverser.list_entries(path):
                if entry.is_file():
                    files.append(entry.name)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"[ProjectSummarizer] Directory scan failed for {path}: {e}")

        readme_content = project_context_manager.extract_description_from_readme(path)

        # Update Status
        await activity_monitor.update_agent_state(sys_tid, "Summarizing", "Project Analysis", "Generating Summary with LLM...")

        # 2. Call LLM
        from app.utils.template import render_template
        prompt_text = render_template(
            "domain/project/project_summary.prompt.j2",
            project_name=name,
            files=files,
            readme_content=readme_content,
            arch_summary=arch_summary
        )

        from app.infrastructure.llm import InternalLLMService
        from app.infrastructure.config.service import SystemConfigService
        model_name = SystemConfigService.get_value("LLM_MODEL")
        response = await InternalLLMService.invoke(
            messages=[{"role": "user", "content": prompt_text}],
            purpose="skill_synthesis",
            temperature=0.3,
            model_name=model_name,
        )

        def parse_json_markdown(text: str) -> dict:
            text = text.strip()
            if text.startswith("```"):
                first_newline = text.find("\n")
                if first_newline != -1:
                    text = text[first_newline:]
                if text.endswith("```"):
                    text = text[:-3]
            return json.loads(text.strip())

        result = parse_json_markdown(response.content)

        # 3. Save Result
        meta_dir = os.path.join(path, ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)

        meta_file = os.path.join(meta_dir, "project.json")
        # Ensure project_id is persisted in the local metadata file
        if project_id is not None:
            result["project_id"] = project_id
        # Ensure authorization defaults exist
        from app.core.hitl.policies import DEFAULT_SENSITIVE_PATTERNS
        result.setdefault("sensitive_patterns", DEFAULT_SENSITIVE_PATTERNS)
        result.setdefault("authorized_paths", [])
        file_utils.write_file(meta_file, dumps(result, indent=2))

        logger.info(f"[ProjectSummarizer] Saved metadata for {name}: {result}")

        # 4. Upload to Member Center & Save Concepts
        concepts = result.get("concepts", [])
        description = result.get("description", "")

        # Resolve Project ID via API Scan (Redundant but safe fallback if logic above failed? No we have early check.)
        # We can reuse project_id resolved above.

        if project_id is not None:
            logger.info(f"[ProjectSummarizer] Resolved Project ID {project_id} for {name}")

            # Upload Summary
            if description:
                try:
                    # This is an async call call now
                    await evocloud_manager.api.update_project(project_id, description)
                    logger.info(f"[ProjectSummarizer] Uploaded summary for {name}")
                    # Invalidate cache to reflect updated description
                    evocloud_manager.invalidate_projects_cache()
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as up_e:
                    logger.error(f"Failed to upload summary: {up_e}")
        else:
            logger.warning(f"[ProjectSummarizer] Could not resolve Project ID for {name}, using default 1")

        # 5. Save Concepts to Memory
        from app.core.memory.lifespan import MemoryLifespanManager
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager
        for c in concepts:
            c_name = c.get("name")
            c_desc = c.get("description")
            if c_name and c_desc:
                from app.core.memory.schemas import Concept
                concept = Concept(name=c_name, description=c_desc, project_id=project_id, related_files=[path])
                await manager.store_concept(concept)

        # Done
        await activity_monitor.end_run(sys_tid, "done")

    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"[ProjectSummarizer] Failed to summarize {name}: {e}")
        await activity_monitor.end_run(sys_tid, "failed")
        # Re-raise to let Celery know it failed (triggering retries if configured)
        raise e


# --- Celery Task ---
@shared_task(name="summarize_project")
def summarize_project_task(name: str, path: str):
    """
    Celery task wrapper for project summarization.
    """

    async def _run_with_flush():
        try:
            await _summarize_project_logic(name, path)
        finally:
            await flush_loop_bound_resources()

    asyncio.run(_run_with_flush())


# --- Main Service Class ---
class ProjectSummarizer:
    """
    Service to dispatch project summarization tasks.
    Now delegates to Celery.
    """

    def __init__(self):
        self._processed = set()

    async def start_worker(self):
        """Deprecated: Worker is now managed by Celery."""
        logger.info("[ProjectSummarizer] Worker is managed by Celery. No internal loop needed.")

    def stop_worker(self):
        pass

    async def add_project(self, name: str, path: str):
        """Add a project to the processing queue (Celery)."""
        if path in self._processed:
            return

        # Check if already has metadata
        meta_path = os.path.join(path, ".evoloop", "project.json")
        if os.path.exists(meta_path):
            self._processed.add(path)
            return

        # Dispatch to Celery
        get_scheduler().send_task("summarize_project", args=(name, path))
        self._processed.add(path)  # Optimistically mark as processed
        logger.debug(f"[ProjectSummarizer] Dispatched {name} to Celery queue")


# Global instance
project_summarizer = ProjectSummarizer()
