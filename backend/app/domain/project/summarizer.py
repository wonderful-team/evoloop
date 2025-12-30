import asyncio
import json
import logging
import os

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.celery_app import celery_app
from app.core.llm.factory import LLMFactory
from app.domain.memory.service import memory_service
from app.domain.project.service import project_context_manager
from app.infrastructure.external.imagicbox import imagicbox_client

logger = logging.getLogger(__name__)


# --- Helper Logic for Summarization (Async) ---
async def _summarize_project_logic(name: str, path: str):
    """
    Core logic to summarize a project using LLM.
    Functionally equivalent to the old _summarize_project method.
    """
    logger.info(f"[ProjectSummarizer] Analyzing {name}...")
    
    # Re-initialize LLM chain here because this runs in a separate process
    llm = LLMFactory.create_llm(temperature=0.3)
    
    prompt = ChatPromptTemplate.from_template("""
    You are a Technical Project Analyst. Analyze the following project information and generate a concise summary.
    
    Project Name: {name}
    File Structure (Top Level): {files}
    README Content (Snippet): {readme}
    
    Return a JSON object with:
    - "description": A concise, one-sentence description of what the project does.
    - "tags": A list of 3-5 technical tags (e.g. "FastAPI", "React", "Tool").
    - "framework": The main framework used (if identifiable, else "Unknown").
    - "concepts": A list of 3-5 core domain concepts/terms found in the project (e.g., specific protocols, architecture components). List of objects {{"name": "...", "description": "..."}}.
    
    JSON Only.
    """)
    parser = JsonOutputParser()
    chain = prompt | llm | parser

    try:
        # 1. Gather Context
        from app.domain.codebase.filter import FileFilter
        f_filter = FileFilter()
        
        files = []
        try:
            # files = [f for f in os.listdir(path) if not f.startswith(".")]
            for f in os.listdir(path):
                if f.startswith("."): 
                    continue
                full_p = os.path.join(path, f)
                if f_filter.should_include(full_p):
                    files.append(f)
        except:
            pass
        
        # Note: project_context_manager needs to be safe to use here.
        # It usually is just file reading.
        readme_content = project_context_manager._extract_description_from_readme(path)
        
        # 2. Call LLM
        result = await chain.ainvoke({
            "name": name,
            "files": ", ".join(files[:20]),
            "readme": readme_content[:2000] # Give more context than the simple snippet
        })
        
        # 3. Save Result
        meta_dir = os.path.join(path, ".evoloop")
        os.makedirs(meta_dir, exist_ok=True)
        
        meta_file = os.path.join(meta_dir, "project.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            
        logger.info(f"[ProjectSummarizer] Saved metadata for {name}: {result}")

        # 4. Upload to Member Center & Save Concepts
        concepts = result.get("concepts", [])
        description = result.get("description", "")
        
        # Resolve Project ID via API Scan
        project_id = 1 # Default fallback
        try:
            # We scan to find the ID associated with this path/name
            projects = await project_context_manager.scan_projects()
            # Match by path first, then name
            matched = None
            abs_path = os.path.abspath(path)
            
            for p in projects:
                # projects from scan have 'path' which is external_path
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
                logger.info(f"[ProjectSummarizer] Resolved Project ID {project_id} for {name}")
                
                # Upload Summary
                if description:
                    try:
                        # This is an async call call now
                        await imagicbox_client.update_project(project_id, description)
                        logger.info(f"[ProjectSummarizer] Uploaded summary for {name}")
                    except Exception as up_e:
                        logger.error(f"Failed to upload summary: {up_e}")
            else:
                logger.warning(f"[ProjectSummarizer] Could not resolve Project ID for {name}, using default 1")

        except Exception as resolve_e:
            logger.warning(f"Error resolving project info: {resolve_e}")

        # 5. Save Concepts to Memory
        for c in concepts:
            c_name = c.get("name")
            c_desc = c.get("description")
            if c_name and c_desc:
                await memory_service.add_concept(name=c_name, description=c_desc, project_id=project_id, related_files=[path])
        
    except Exception as e:
        logger.error(f"[ProjectSummarizer] Failed to summarize {name}: {e}")
        # Re-raise to let Celery know it failed (triggering retries if configured)
        raise e


# --- Celery Task ---
@celery_app.task(name="summarize_project")
def summarize_project_task(name: str, path: str):
    """
    Celery task wrapper for project summarization.
    """
    asyncio.run(_summarize_project_logic(name, path))


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
        self._processed.add(path) # Optimistically mark as processed
        logger.debug(f"[ProjectSummarizer] Dispatched {name} to Celery queue")

# Global instance
project_summarizer = ProjectSummarizer()
