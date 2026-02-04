"""
Memory Replay - Retrieves relevant memories during awakening.
"""

import logging
import os

from app.core.environment.models import (
    EpisodeSummary,
    ConceptSummary,
    MemoryContext,
)

logger = logging.getLogger(__name__)


async def replay_memory(project_id: int | None = None) -> MemoryContext:
    """
    Retrieve relevant memories for the awakening context.
    
    Args:
        project_id: Optional project ID to scope memory retrieval.
        
    Returns:
        MemoryContext with episodes, concepts, and journal highlights.
    """
    episodes = []
    concepts = []
    journal_highlights = ""
    
    # 1. Retrieve recent episodes from Long-Term Memory
    if project_id:
        try:
            from app.core.memory import memory_manager
            
            raw_experience = await memory_manager.long_term.retrieve_experience(
                goal="Recent tasks",
                project_id=project_id,
                top_k=5,
            )
            episodes = _parse_episodes(raw_experience)
        except Exception as e:
            logger.warning(f"Failed to retrieve episodes: {e}")
    
    # 2. Retrieve project concepts from Semantic Memory
    if project_id:
        try:
            from app.core.memory import memory_manager
            
            concepts_text = await memory_manager.long_term.get_project_concepts(project_id)
            concepts = _parse_concepts(concepts_text)
        except Exception as e:
            logger.warning(f"Failed to retrieve concepts: {e}")
    
    # 3. Read journal highlights (last 10 lines)
    journal_highlights = _read_journal_highlights()
    
    return MemoryContext(
        episodes=episodes,
        concepts=concepts,
        journal_highlights=journal_highlights,
    )


def _parse_episodes(raw_text: str) -> list[EpisodeSummary]:
    """Parse episode text into structured summaries."""
    episodes = []
    
    if not raw_text:
        return episodes
    
    # Expected format: "[date] goal -> result"
    import re
    pattern = r"\[([^\]]+)\]\s+(.+?)\s*[-→>]+\s*(\w+)"
    
    for match in re.finditer(pattern, raw_text):
        episodes.append(EpisodeSummary(
            date=match.group(1).strip(),
            goal=match.group(2).strip(),
            result=match.group(3).strip().upper(),
        ))
    
    return episodes[:5]  # Limit to 5


def _parse_concepts(raw_text: str) -> list[ConceptSummary]:
    """Parse concept text into structured summaries."""
    concepts = []
    
    if not raw_text:
        return concepts
    
    # Simple line-by-line parsing
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        # Try to split on colon or just use the line as name
        if ":" in line:
            name, desc = line.split(":", 1)
            concepts.append(ConceptSummary(name=name.strip(), description=desc.strip()))
        else:
            concepts.append(ConceptSummary(name=line))
    
    return concepts[:10]  # Limit to 10


def _read_journal_highlights() -> str:
    """Read the last 10 lines from journal.md."""
    try:
        from app.core.config import settings
        
        journal_path = os.path.join(settings.BRAIN_MEMORY_ROOT, "knowledge", "journal.md")
        if not os.path.exists(journal_path):
            return ""
        
        with open(journal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Get last 10 non-empty lines
        recent_lines = [l.strip() for l in lines if l.strip()][-10:]
        return "\n".join(recent_lines)
    
    except Exception as e:
        logger.warning(f"Failed to read journal: {e}")
        return ""
