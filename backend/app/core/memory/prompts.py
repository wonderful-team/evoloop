"""
Memory System Prompt Builders

Standardizes LLM prompts for memory-related operations (Extraction, Pruning, Retrieval).
Separates static system instructions from dynamic context to support prompt caching.
"""
import logging
from typing import List, Optional

from app.utils import render_template

logger = logging.getLogger(__name__)


class MemoryExtractionPromptBuilder:
    """Builder for knowledge extraction prompts."""

    def __init__(
        self,
        readme_summary: str = "",
        pending_todos: str = "",
        existing_memories: str = "",
        multi_source_context: str = "",
        messages_text: str = "",
        summary: Optional[str] = None,
    ):
        self.readme_summary = readme_summary
        self.pending_todos = pending_todos
        self.existing_memories = existing_memories
        self.multi_source_context = multi_source_context
        self.messages_text = messages_text
        self.summary = summary

    async def build(self) -> List[dict]:
        """Builds standardized message list for extraction."""

        # 1. Static System Prompt (Persona & Rules)
        # Note: In a full caching setup, we'd split high-churn context into a separate User Message "ticket"
        # but for now we'll consolidate into a clean J2 template.

        template_vars = {
            "readme_summary": self.readme_summary,
            "pending_todos": self.pending_todos,
            "existing_memories": self.existing_memories,
            "multi_source_context": self.multi_source_context,
            "messages_text": self.messages_text,
            "summary": self.summary,
        }
        
        rendered = render_template("core/memory/auto_extraction.prompt.j2", **template_vars)
        
        return [
            {"role": "system", "content": "You are a Senior Knowledge Architect. Extract high-impact strategic memories while strictly avoiding redundancy and pollution."},
            {"role": "user", "content": rendered}
        ]


class MemoryPruningPromptBuilder:
    """Builder for memory pruning and consolidation prompts."""
    
    def __init__(
        self,
        strategy: str,  # 'semantic_pruning' | 'consolidation'
        project_root: str = "",
        readme: str = "",
        memories_text: str = ""
    ):
        self.strategy = strategy
        self.project_root = project_root
        self.readme = readme
        self.memories_text = memories_text

    async def build(self) -> List[dict]:
        """Builds standardized message list for pruning."""
        template_name = "core/memory/pruning_semantic.prompt.j2" if self.strategy == "semantic_pruning" else "core/memory/pruning_consolidation.prompt.j2"
        
        template_vars = {
            "project_root": self.project_root,
            "readme": self.readme,
            "memories_text": self.memories_text,
            "content": self.memories_text, # For consolidation.prompt.j2 backwards compatibility
        }
        
        rendered = render_template(template_name, **template_vars)
        
        system_role = "You are a precise librarian evaluating information redundancy."
        if self.strategy == "consolidation":
            system_role = "You are a Knowledge Architect specialized in distilling fragmented information."
            
        return [
            {"role": "system", "content": system_role},
            {"role": "user", "content": rendered}
        ]


class MemoryRetrievalPromptBuilder:
    """Builder for memory retrieval refinement prompts."""
    
    def __init__(
        self,
        query: str,
        memories: List[dict],
        recent_tools: List[str] = None,
        max_selections: int = 5
    ):
        self.query = query
        self.memories = memories
        self.recent_tools = recent_tools or []
        self.max_selections = max_selections

    async def build(self) -> List[dict]:
        """Builds standardized message list for retrieval selection."""
        template_vars = {
            "query": self.query,
            "memories": self.memories,
            "recent_tools": self.recent_tools,
            "max_selections": self.max_selections
        }
        
        rendered = render_template("core/memory/retrieval_selection.prompt.j2", **template_vars)
        
        return [
            {"role": "system", "content": "You are a memory relevance selector. Your goal is to identify which items from the candidate pool are truly essential for the user's query."},
            {"role": "user", "content": rendered}
        ]
