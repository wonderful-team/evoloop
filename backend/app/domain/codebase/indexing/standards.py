import logging
import os
import random

from langchain_core.messages import HumanMessage, SystemMessage

from app.infrastructure.llm.factory import LLMFactory
from app.core.memory import memory_manager
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

        # 2. Prepare Context
        snippets = []
        for fpath in sample_files:
            try:
                content, _ = read_file_content(fpath)
                if content:
                    # Truncate to avoid context overflow if files are huge
                    snippets.append(f"--- File: {os.path.basename(fpath)} ---\n{content[:2000]}\n")
            except Exception:
                pass

        combined_context = "\n".join(snippets)

        # 3. LLM Analysis
        llm = LLMFactory.create_llm(temperature=0.1)  # Low temp for factual analysis

        system_prompt = """You are a Lead Architect conducting a Code Audit.
        Your goal is to extract the IMPLICIT CODING STANDARDS and PATTERNS from the provided code samples.
        Do NOT critique the code. Describe the 'Way of Working'.

        Focus on:
        1. Naming Conventions (Snake case? Camel case? Prefix rules?)
        2. Typing (Strict type hints? No types? Pydantic?)
        3. Documentation (Docstring style? Google/NumPy/Sphinx? Comments?)
        4. Architectual Patterns (Repository pattern? Service layer? MVC?)
        5. Error Handling (Exceptions? Return values?)
        6. Libraries (Key libs used frequently?)

        Output a concise List of Rules that a new developer should follow."""

        user_prompt = f"Here are samples from the codebase:\n\n{combined_context}\n\nExtract the Coding Standards."

        try:
            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            standards_report = response.content

            logger.info("[StandardsAnalyst] Analysis Complete. Saving to Memory.")

            # 4. Save to Memory
            # We treat this as a high-level concept: "Project Standards"
            from app.core.memory.interfaces.long_term import Concept
            concept = Concept("Project Coding Standards", standards_report, project_id, sample_files)
            await memory_manager.long_term.store_concept(concept)

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
