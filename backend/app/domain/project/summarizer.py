import asyncio
import logging
import os

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.infrastructure.queue.celery import celery_app
from app.core.evocloud import evocloud_manager
from app.core.memory import memory_manager
from app.core.monitoring.activity import activity_monitor
from app.domain.codebase.filter import FileFilter
from app.domain.project.service import project_context_manager
from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.llm.factory import LLMFactory
from app.utils import file as file_utils
from app.utils import json as json_utils
from app.utils.async_utils import flush_loop_bound_resources

logger = logging.getLogger(__name__)


# --- Helper Logic for Summarization (Async) ---
async def _summarize_project_logic(name: str, path: str):
    """
    Core logic to summarize a project using LLM.
    Functionally equivalent to the old _summarize_project method.
    """
    logger.info(f"[ProjectSummarizer] Analyzing {name}...")

    # 0. Resolve Project ID Early (Used for Graph Lookup)
    project_id = 1  # Default
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
    except Exception as e:
        logger.warning(f"Early project ID resolution failed: {e}")

    # Start Activity
    sys_tid = f"sys:{project_id}:summarization"
    await activity_monitor.start_run(sys_tid, f"Summarize Project: {name}")
    await activity_monitor.update_agent_state(
        sys_tid, "Summarizing", "Project Analysis", "Gathering Context..."
    )

    try:
        # 1. Fetch Deep Architectural Summary from Graph (if available)
        arch_summary = "Not available yet."
        try:
            driver = await get_graph_db()
            async with driver.session() as session:
                # Check for Root Directory Node
                # Logic: path should match exactly.
                # Note: DirectorySummarizer logic ensures path has no trailing slash usually, or normalized.
                # We try exact match first.
                query = """
                MATCH (d:Directory {path: $path, project_id: $pid})
                RETURN d.description as summary
                """
                result = await session.run(query, path=path, pid=project_id)
                record = await result.single()
                if record and record["summary"]:
                    arch_summary = record["summary"]
                    logger.info(f"[ProjectSummarizer] Found existing architectural summary for {name}")
                else:
                    # Try fallback: maybe path needs trailing slash?
                    pass
        except Exception as e:
            logger.warning(f"[ProjectSummarizer] Failed to fetch graph summary: {e}")

        # Update Status
        await activity_monitor.update_agent_state(
            sys_tid, "Summarizing", "Project Analysis", "Reading Files & Context..."
        )

        # 1. Gather Context (Files)
        f_filter = FileFilter()

        files = []
        try:
            for f in os.listdir(path):
                if f.startswith("."):
                    continue
                full_p = os.path.join(path, f)
                if f_filter.should_include(full_p):
                    files.append(f)
        except Exception:
            pass

        readme_content = project_context_manager.extract_description_from_readme(path)

        # Update Status
        await activity_monitor.update_agent_state(
            sys_tid, "Summarizing", "Project Analysis", "Generating Summary with LLM..."
        )

        # 2. Call LLM
        from app.utils import render_template
        prompt_text = render_template(
            "project/project_summary.prompt.j2",
            project_name=name,
            files=files,
            readme_content=readme_content,
            arch_summary=arch_summary
        )

        llm = LLMFactory.create_llm(temperature=0.3)
        response = await llm.ainvoke(prompt_text)
        
        from app.core.output.parsers import JsonOutputParser
        parser = JsonOutputParser()
        result = parser.parse(response.content if hasattr(response, 'content') else str(response))

        # 3. Save Result
        meta_dir = os.path.join(path, ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)

        meta_file = os.path.join(meta_dir, "project.json")
        file_utils.write_file(meta_file, json_utils.dumps(result, indent=2))

        logger.info(f"[ProjectSummarizer] Saved metadata for {name}: {result}")

        # 4. Upload to Member Center & Save Concepts
        concepts = result.get("concepts", [])
        description = result.get("description", "")

        # Resolve Project ID via API Scan (Redundant but safe fallback if logic above failed? No we have early check.)
        # We can reuse project_id resolved above.

        if project_id:
            logger.info(f"[ProjectSummarizer] Resolved Project ID {project_id} for {name}")

            # Upload Summary
            if description:
                try:
                    # This is an async call call now
                    await evocloud_manager.api.update_project(project_id, description)
                    logger.info(f"[ProjectSummarizer] Uploaded summary for {name}")
                except Exception as up_e:
                    logger.error(f"Failed to upload summary: {up_e}")
        else:
            logger.warning(f"[ProjectSummarizer] Could not resolve Project ID for {name}, using default 1")

        # 5. Save Concepts to Memory
        for c in concepts:
            c_name = c.get("name")
            c_desc = c.get("description")
            if c_name and c_desc:
                from app.core.memory.interfaces.long_term import Concept
                concept = Concept(c_name, c_desc, project_id, [path])
                await memory_manager.long_term.store_concept(concept)

        # Done
        await activity_monitor.end_run(sys_tid, "done")

    except Exception as e:
        logger.error(f"[ProjectSummarizer] Failed to summarize {name}: {e}")
        await activity_monitor.end_run(sys_tid, "failed")
        # Re-raise to let Celery know it failed (triggering retries if configured)
        raise e


# --- Celery Task ---
@celery_app.task(name="summarize_project")
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
        summarize_project_task.delay(name, path)
        self._processed.add(path)  # Optimistically mark as processed
        logger.debug(f"[ProjectSummarizer] Dispatched {name} to Celery queue")


# Global instance
project_summarizer = ProjectSummarizer()
