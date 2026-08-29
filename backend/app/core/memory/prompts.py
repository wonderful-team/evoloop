"""
Memory System Prompt Builders

Standardizes LLM prompts for memory-related operations (Extraction, Pruning, Retrieval).
Separates static system instructions from dynamic context to support prompt caching.
"""

import logging

from app.utils.template import render_template

logger = logging.getLogger(__name__)


class MemoryPruningPromptBuilder:
    """Builder for memory pruning and consolidation prompts."""

    def __init__(
        self,
        strategy: str,  # 'semantic_pruning' | 'consolidation'
        project_root: str = "",
        readme: str = "",
        memories_text: str = "",
    ):
        self.strategy = strategy
        self.project_root = project_root
        self.readme = readme
        self.memories_text = memories_text

    async def build(self) -> list[dict]:
        """Builds standardized message list for pruning."""
        template_name = (
            "core/memory/pruning_semantic.prompt.j2"
            if self.strategy == "semantic_pruning"
            else "core/memory/pruning_consolidation.prompt.j2"
        )

        template_vars = {
            "project_root": self.project_root,
            "readme": self.readme,
            "memories_text": self.memories_text,
            "content": self.memories_text,  # For consolidation.prompt.j2 backwards compatibility
        }

        rendered = render_template(template_name, **template_vars)

        system_role = "You are a precise librarian evaluating information redundancy."
        if self.strategy == "consolidation":
            system_role = "You are a Knowledge Architect specialized in distilling fragmented information."

        return [
            {"role": "system", "content": system_role},
            {"role": "user", "content": rendered},
        ]
