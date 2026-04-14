import logging
import os
import random

from app.utils import render_template
from app.utils.file import read_file_content

logger = logging.getLogger(__name__)


class ProjectStandardsAnalyst:
    """
    Analyzes codebase to extract implicit coding standards, patterns, and preferences.
    Running this allows the Agent to 'mimic' the existing style.
    """

    async def analyze_standards(self, project_id: int, project_path: str):
        logger.info(f"[StandardsAnalyst] Starting analysis for project {project_id} at {project_path}")

        # 1. Sample Files
        # We want "Core" files, not just random scripts.
        # Heuristic: Pick files from 'app', 'domain', 'core', 'src' if they exist.
        sample_files = self._sample_files(project_path, count=15)

        if not sample_files:
            logger.warning("[StandardsAnalyst] Not enough files to analyze.")
            return

        # 2. Analysis Step handled below in Step 3

        # 3. LLM Analysis - Prepare file info for template
        files_info = []
        for fpath in sample_files:
            try:
                content, _ = read_file_content(fpath)
                if content:
                    files_info.append({"path": os.path.basename(fpath), "content": content[:2000]})
            except Exception:
                pass

        prompt_text = render_template(
            "codebase/code_audit.prompt.j2",
            standards="General implicit standards extraction",
            files=files_info
        )

        try:
            from app.core.llm import InternalLLMService
            response = await InternalLLMService.invoke(
                messages=[{"role": "user", "content": prompt_text}],
                purpose="audit_summary",
                temperature=0.1,
            )
            standards_report = response.content if hasattr(response, 'content') else str(response)

            logger.info("[StandardsAnalyst] Analysis Complete. Saving to Memory.")

            # 4. Save to Memory
            # We treat this as a high-level concept: "Project Standards"
            from app.core.memory.lifespan import MemoryLifespanManager
            if not MemoryLifespanManager.is_initialized():
                await MemoryLifespanManager.ainitialize()
            container = MemoryLifespanManager.get_container()
            manager = container.memory_manager
            from app.core.memory.interfaces.long_term import Concept
            concept = Concept("Project Coding Standards", standards_report, project_id, sample_files)
            await manager.long_term.store_concept(concept)

            # Also save as generic preference?
            # Ideally this feeds into the Coder's system prompt dynamically.
            # For now, Memory is the storage.

            return standards_report

        except Exception as e:
            logger.error(f"[StandardsAnalyst] Analysis Failed: {e}")

    def _sample_files(self, root_path: str, count: int = 15) -> list[str]:
        valid_exts = (".py", ".js", ".ts", ".go", ".java", ".rs")
        candidates = []

        for root, _dirs, files in os.walk(root_path):
            if any(p in root for p in [".git", "__pycache__", "node_modules", "venv", ".venv"]):
                continue

            for f in files:
                if f.endswith(valid_exts):
                    candidates.append(os.path.join(root, f))

        # Prioritize core directories
        core_candidates = [
            f for f in candidates if "core" in f or "domain" in f or "app" in f
        ]

        selection = []
        if len(core_candidates) >= count:
            selection = random.sample(core_candidates, count)
        elif len(candidates) >= count:
            selection = random.sample(candidates, count)
        else:
            selection = candidates

        return selection


# Global Instance
project_standards_analyst = ProjectStandardsAnalyst()
