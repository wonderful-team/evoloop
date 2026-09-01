"""
Two-Tier Memory Architecture - Inspired by Claude Code's CLAUDE.md system.

Tier 1 (Hot Memory): MEMORY.md - Always loaded on session start
Tier 2 (Cold Memory): Full memory store - Searched on demand

Architecture:
    ~/.evoloop/memory/
    ├── MEMORY.md          # Tier 1: Always loaded (200 lines / 25KB max)
    │   ├── Architecture   # 25 lines - System design, components
    │   ├── Decisions      # 25 lines - ADRs, design choices
    │   ├── Patterns       # 25 lines - Recurring solutions
    │   ├── Gotchas        # 20 lines - Warnings, pitfalls
    │   ├── Progress       # 30 lines - Recent work (decays)
    │   └── Context        # 15 lines - Temp context (decays fast)
    ├── private/           # Tier 2: Search on demand
    └── team/              # Tier 2: Search on demand

Budget System:
- Fixed line budgets per section
- Ranked by: confidence × access_count
- Unused budget redistributes to overflowing sections
- Overflow indicates: "See cold memory for more"

Usage:
    from app.core.memory.config import MemoryConfig
    from app.core.memory.store import MemoryStore
    from app.core.memory.retrieval import MemoryRetriever

    config = MemoryConfig.from_settings()
    storage = MemoryStore(str(config.user_memory_root))
    retriever = MemoryRetriever(storage=storage, config=config)

    manager = TwoTierMemoryManager(storage=storage, config=config)

    # Tier 1: Always loaded
    hot_memory = await manager.get_hot_memory()

    # Tier 2: Search on demand (via retriever)
    cold_results = await retriever.find_relevant("docker deployment")

    # Auto-generate Tier 1 from Tier 2
    await manager.regenerate_memory_md()
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from app.core.config import settings
from app.core.memory.constants import MAX_TOTAL_BYTES, MAX_TOTAL_LINES
from app.core.memory.models import (
    MemoryEntry,
    MemorySearchResult,
    MemoryTier,
    MemoryType,
)
from app.core.memory.retrieval import MemoryRetriever
from app.core.memory.schemas import MemorySectionEntry
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class MemorySection(DynamicBaseModel):
    """A section in MEMORY.md."""

    name: str
    title: str
    budget: int
    entries: list[MemorySectionEntry] = Field(default_factory=list)

    def to_markdown(self, max_lines: int | None = None) -> str:
        """Generate markdown for this section."""
        max_lines = max_lines or self.budget

        lines = [f"## {self.title}", ""]

        for entry in self.entries[:max_lines]:
            title = entry.title
            description = entry.description
            lines.append(f"- **{title}**: {description}")

        # Overflow indicator
        if len(self.entries) > max_lines:
            overflow_count = len(self.entries) - max_lines
            lines.append(f"\n*... and {overflow_count} more in cold memory*")

        return "\n".join(lines) + "\n\n"


class TwoTierMemoryManager:
    """
    Two-tier memory system with budget management.

    Tier 1 (Hot): MEMORY.md - Always loaded, limited size
    Tier 2 (Cold): Full storage - Searched on demand
    """

    # Default budget allocation (lines per section)
    DEFAULT_BUDGETS = {
        "architecture": 25,
        "decisions": 25,
        "patterns": 25,
        "gotchas": 20,
        "progress": 30,
        "context": 15,
    }

    # Section definitions
    SECTIONS = {
        "architecture": "Architecture",
        "decisions": "Key Decisions",
        "patterns": "Patterns & Conventions",
        "gotchas": "Gotchas & Warnings",
        "progress": "Recent Progress",
        "context": "Current Context",
    }

    def __init__(
        self,
        storage,
        config=None,
        root_path: Path | None = None,
        analyzer=None,
        project_id: int | None = None,
    ):
        """
        Initialize two-tier memory manager.

        Args:
            storage: Storage backend (required)
            config: Memory configuration. Uses defaults if None.
            root_path: Root path for memory files (legacy, prefer config).
            analyzer: Quality analyzer for scoring.
            project_id: Project scope for filtering memories. None = all projects (global).
        """
        self._storage = storage
        self._config = config
        self._analyzer = analyzer
        self._retriever: Any = None
        self._project_id = project_id

        if root_path is not None:
            # Explicit root path takes priority (used by project-mode memory)
            self.root = Path(root_path)
        elif config is not None:
            self.root = config.user_memory_root
        else:
            self.root = Path(settings.BRAIN_MEMORY_ROOT)

        self.memory_md_path = self.root / "MEMORY.md"
        self.budgets = self.DEFAULT_BUDGETS.copy()

    async def get_hot_memory(self) -> str:
        """
        Get Tier 1 memory (MEMORY.md) - always loaded.

        Returns truncated content if exceeds limits.
        """
        if not self.memory_md_path.exists():
            # Generate if doesn't exist
            await self.regenerate_memory_md()

        content = await self._read_truncated()
        return content

    async def search_cold_memory(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[MemoryEntry]:
        """
        Search Tier 2 cold memory (full storage) using smart retrieval.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of relevant memory entries
        """
        if self._retriever is None:
            self._retriever = MemoryRetriever(
                self._storage,
                config=self._config,
                max_results=max_results,
            )
        self._retriever.max_results = max_results
        return await self._retriever.find_relevant(query)

    async def regenerate_memory_md(self) -> None:
        """
        Regenerate MEMORY.md from cold memory.

        Algorithm:
        1. Collect all memories from cold storage
        2. Score by: confidence × access_count × freshness
        3. Allocate to sections by type
        4. Apply budgets with redistribution
        5. Write to MEMORY.md
        """
        logger.info("[TwoTier] Regenerating MEMORY.md from cold memory")

        # Collect all memories
        all_memories = await self._collect_all_memories()

        # Score and rank
        scored = self._score_memories(all_memories)

        # Allocate to sections
        sections = self._allocate_to_sections(scored)

        # Apply budgets with redistribution
        budgeted = self._apply_budgets(sections)

        # Generate markdown
        content = self._generate_memory_md(budgeted)

        # Write to file
        await self._write_memory_md(content)

        logger.info("[TwoTier] MEMORY.md regenerated successfully")

    async def update_section(
        self,
        section_name: str,
        entries: list[MemorySectionEntry],
    ) -> None:
        """
        Update a specific section in MEMORY.md.

        Preserves other sections.
        """
        if not self.memory_md_path.exists():
            await self.regenerate_memory_md()
            return

        # Read current content
        content = self.memory_md_path.read_text(encoding="utf-8")

        # Parse sections
        sections = self._parse_memory_md(content)

        # Update specified section
        if section_name in sections:
            sections[section_name]["entries"] = entries

        # Regenerate with updated section
        new_content = self._generate_memory_md(sections)
        await self._write_memory_md(new_content)

    async def add_to_section(
        self,
        section_name: str,
        entry: MemorySectionEntry,
    ) -> bool:
        """
        Add an entry to a section, respecting budget.

        Returns True if added, False if budget full (should go to cold memory).
        """
        if not self.memory_md_path.exists():
            await self.regenerate_memory_md()

        content = self.memory_md_path.read_text(encoding="utf-8")
        sections = self._parse_memory_md(content)

        section = sections.get(section_name)
        if not section:
            return False

        budget = self.budgets.get(section_name, 25)
        if len(section["entries"]) >= budget:
            return False  # Budget full

        section["entries"].append(entry)

        new_content = self._generate_memory_md(sections)
        await self._write_memory_md(new_content)

        return True

    async def get_section_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for each section."""
        if not self.memory_md_path.exists():
            await self.regenerate_memory_md()

        content = self.memory_md_path.read_text(encoding="utf-8")
        sections = self._parse_memory_md(content)

        stats = {}
        for name, section in sections.items():
            budget = self.budgets.get(name, 25)
            stats[name] = {
                "budget": budget,
                "used": len(section["entries"]),
                "remaining": budget - len(section["entries"]),
                "overflow": len(section["entries"]) > budget,
            }

        return stats

    async def _collect_all_memories(self) -> list[MemorySearchResult]:
        """Collect all memories from cold storage, filtered by project_id if set."""
        entries = await self._storage.list_all(limit=1000, project_id=self._project_id)

        return entries

    def _score_memories(
        self,
        entries: list[MemorySearchResult],
    ) -> list[tuple[MemorySearchResult, float]]:
        """
        Score memories for ranking in MEMORY.md.

        Formula: confidence × access_count × freshness
        """
        now = datetime.utcnow()
        scored = []

        for entry in entries:
            # Confidence (now projected in search results)
            confidence = entry.confidence

            # Access count (from quality analyzer if available)
            access_count = 0
            if self._analyzer:
                access_count = self._analyzer.get_access_count(entry.id)

            # Freshness (exponential decay)
            age_days = (now - entry.updated_at).days
            freshness = self._calculate_freshness(entry.type, age_days)

            # Tier weight (Strategic = 2.0x boost)
            tier_multiplier = 2.0 if entry.tier == MemoryTier.STRATEGIC else 1.0

            # Combined score: utility and strategic tier are the primary drivers
            score = (
                (entry.utility_score or confidence)
                * (1 + access_count * 0.1)
                * freshness
                * tier_multiplier
            )
            scored.append((entry, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _calculate_freshness(
        self,
        mem_type: MemoryType,
        age_days: int,
    ) -> float:
        """Calculate freshness based on type-specific lifespan."""
        # Type-specific lifespans (from Claude Code)
        lifespans = {
            MemoryType.USER: None,  # Permanent
            MemoryType.FEEDBACK: 30,  # 30 days
            MemoryType.PROJECT: None,  # Permanent
            MemoryType.REFERENCE: 7,  # 7 days
        }

        lifespan = lifespans.get(mem_type)
        if lifespan is None:
            return 1.0  # No decay

        # Linear decay to 0 over lifespan
        return max(0.0, 1.0 - (age_days / lifespan))

    def _allocate_to_sections(
        self,
        scored: list[tuple[MemorySearchResult, float]],
    ) -> dict[str, dict[str, Any]]:
        """Allocate memories to sections based on type."""
        sections: dict[str, dict[str, Any]] = {
            name: {"title": title, "entries": []}
            for name, title in self.SECTIONS.items()
        }

        # Type to section mapping
        type_mapping = {
            MemoryType.PROJECT: "architecture",
            MemoryType.USER: "patterns",
            MemoryType.FEEDBACK: "gotchas",
        }

        # Track seen titles to prevent duplicates in the map (even for different IDs)
        seen_titles = set()

        for entry, score in scored:
            # Simple title deduplication (Normalized)
            # This prevents "Conclusion: A" and "Conclusion: A" from appearing twice
            title_norm = entry.title.strip().lower()
            if title_norm in seen_titles:
                continue

            # Determine section by type
            section_name = type_mapping.get(entry.type, "context")

            # Add to section and mark as seen
            sections[section_name]["entries"].append(
                {
                    "id": entry.id,
                    "title": entry.title,
                    "description": entry.description[:500],
                    "score": score,
                    "type": entry.type.value,
                    "tier": entry.tier.value,
                }
            )
            seen_titles.add(title_norm)

        return sections

    def _apply_budgets(
        self,
        sections: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """
        Apply budget constraints with redistribution.

        Algorithm:
        1. Allocate within initial budget
        2. Collect unused budget
        3. Redistribute to overflowing sections
        """
        result = {}
        unused_budget = 0
        overflowing = []

        # First pass: allocate within budget
        for name, section in sections.items():
            budget = self.budgets.get(name, 25)
            entries = section["entries"]

            if len(entries) <= budget:
                # Within budget
                result[name] = {
                    **section,
                    "entries": entries,
                    "overflow": False,
                }
                unused_budget += budget - len(entries)
            else:
                # Overflow
                result[name] = {
                    **section,
                    "entries": entries[:budget],
                    "overflow": True,
                    "overflow_count": len(entries) - budget,
                }
                overflowing.append(name)

        # Second pass: redistribute unused budget
        if overflowing and unused_budget > 0:
            redistribution = unused_budget // len(overflowing)

            for name in overflowing:
                section = result[name]
                original_overflow = section["overflow_count"]

                # Take from overflow
                additional = min(redistribution, original_overflow)
                current_len = len(section["entries"])
                all_entries = sections[name]["entries"]

                section["entries"] = all_entries[: current_len + additional]
                section["overflow_count"] = original_overflow - additional
                section["overflow"] = section["overflow_count"] > 0

        return result

    def _generate_memory_md(
        self,
        sections: dict[str, dict[str, Any]],
    ) -> str:
        """Generate MEMORY.md content."""
        lines = [
            "# Project Memory",
            "",
            f"*Auto-generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
            "",
            "This file contains the most important project knowledge.",
            "For full details, search the memory system.",
            "",
        ]

        # Section order (important first)
        section_order = [
            "architecture",
            "decisions",
            "patterns",
            "gotchas",
            "progress",
            "context",
        ]

        for name in section_order:
            if name in sections:
                section = sections[name]
                section_obj = MemorySection(
                    name=name,
                    title=section["title"],
                    budget=self.budgets.get(name, 25),
                    entries=section["entries"],
                )
                lines.append(section_obj.to_markdown())

        return "\n".join(lines)

    def _parse_memory_md(self, content: str) -> dict[str, dict[str, Any]]:
        """Parse MEMORY.md into sections."""
        sections = {}
        current_section = None
        current_entries = []

        for line in content.split("\n"):
            # Section header
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = {
                        "title": self.SECTIONS.get(current_section, current_section),
                        "entries": current_entries,
                    }

                section_title = line[3:].strip()
                # Find section name from title
                current_section = None
                for name, title in self.SECTIONS.items():
                    if title.lower() in section_title.lower():
                        current_section = name
                        break

                if not current_section:
                    current_section = section_title.lower().replace(" ", "_")

                current_entries = []

            # Entry line
            elif line.startswith("- **") and current_section:
                # Parse: - **Title**: Description
                match = re.match(r"- \*\*(.+?)\*\*: (.+)", line)
                if match:
                    title, desc = match.groups()
                    current_entries.append(
                        {
                            "title": title,
                            "description": desc,
                        }
                    )

        # Don't forget last section
        if current_section:
            sections[current_section] = {
                "title": self.SECTIONS.get(current_section, current_section),
                "entries": current_entries,
            }

        return sections

    async def _write_memory_md(self, content: str) -> None:
        """Write to MEMORY.md."""
        await asyncio.to_thread(
            self._write_sync,
            content,
        )

    def _write_sync(self, content: str) -> None:
        """Synchronous write."""
        self.memory_md_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_md_path.write_text(content, encoding="utf-8")

    async def _read_truncated(self) -> str:
        """Read MEMORY.md with truncation."""
        if not self.memory_md_path.exists():
            return self._generate_default_content()

        return await asyncio.to_thread(
            self._read_truncated_sync,
        )

    def _read_truncated_sync(self) -> str:
        """Synchronous read with truncation."""
        content = self.memory_md_path.read_text(encoding="utf-8")

        # Check byte limit
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_TOTAL_BYTES:
            # Truncate to byte limit
            truncated = content_bytes[:MAX_TOTAL_BYTES]
            content = truncated.decode("utf-8", errors="ignore")
            content += "\n\n*[Content truncated due to size limit]*"

        # Check line limit
        lines = content.split("\n")
        if len(lines) > MAX_TOTAL_LINES:
            lines = lines[:MAX_TOTAL_LINES]
            lines.append("\n*[Content truncated due to line limit]*")
            content = "\n".join(lines)

        return content

    def _generate_default_content(self) -> str:
        """Generate default MEMORY.md content."""
        return """# Project Memory

*No memories yet. Start a conversation to build project knowledge.*

## How to Use

- **Architecture**: System design and component relationships
- **Key Decisions**: Important design choices and ADRs
- **Patterns & Conventions**: Recurring solutions and coding standards
- **Gotchas & Warnings**: Common pitfalls and how to avoid them
- **Recent Progress**: What you've been working on recently
- **Current Context**: Temporary context for the current session

Memories are automatically extracted from conversations and ranked by importance.
"""
