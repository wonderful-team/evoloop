"""
Memory Replay - Retrieves relevant memories during awakening.
"""

import logging
import os

from app.core.environment.models import (
    ConceptSummary,
    EpisodeSummary,
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
    from app.core.memory.lifespan import MemoryLifespanManager

    episodes = []
    concepts = []

    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()
    container = MemoryLifespanManager.get_container()
    manager = container.memory_manager

    # 1. Retrieve recent episodes from Long-Term Memory
    # Note: project_id can be 0 (global mode), skip in that case
    if project_id is not None and project_id != 0:
        try:
            raw_experience = await manager.long_term.retrieve_experience(
                goal="Recent tasks",
                project_id=project_id,
                top_k=5,
            )
            episodes = _parse_episodes(raw_experience)
        except Exception as e:
            logger.warning(f"Failed to retrieve episodes: {e}")

    # 2. Retrieve project concepts from Semantic Memory
    try:
        # 2a. Global concepts (e.g. environment facts)
        global_concepts_text = await manager.long_term.get_project_concepts(0)
        concepts.extend(_parse_concepts(global_concepts_text))

        # 2b. Project-specific concepts
        if project_id and project_id != 0:
            project_concepts_text = await manager.long_term.get_project_concepts(project_id)
            concepts.extend(_parse_concepts(project_concepts_text))

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


def _parse_concepts(raw_data: str | list[str]) -> list[ConceptSummary]:
    """Parse concept text or list into structured summaries."""
    concepts = []

    if not raw_data:
        return concepts

    # Handle list of strings
    lines = raw_data if isinstance(raw_data, list) else raw_data.splitlines()

    # Simple line-by-line parsing
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Try to split on colon or just use the line as name
        # Fix: If it starts with android_layout:, we might have name:detail:desc
        if line.startswith("android_layout:"):
            parts = line.split(":", 2)
            if len(parts) >= 2:
                name = ":".join(parts[:2])
                desc = parts[2].strip() if len(parts) > 2 else ""
                concepts.append(ConceptSummary(name=name, description=desc))
            else:
                concepts.append(ConceptSummary(name=line))
        elif ":" in line:
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

        with open(journal_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Get last 10 non-empty lines
        recent_lines = [l.strip() for l in lines if l.strip()][-10:]
        return "\n".join(recent_lines)

    except Exception as e:
        logger.warning(f"Failed to read journal: {e}")
        return ""
