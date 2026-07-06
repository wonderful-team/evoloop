"""
PromptAssemblyBuilder — 链式提示词组装器

将 System Prompt 拆分为独立段落（Segment），每段可独立开关、缓存、调试。
取代将所有内容硬编码在单个 Jinja2 模板中的做法。

Usage:
    prompt = (
        PromptAssemblyBuilder()
        .add_role("You are a code specialist.")
        .add_skills_index(skills_frontmatter)
        .add_long_term_memory(memory_text)
        .add_section("constraints", "Do not modify files outside cwd.")
        .build()
    )
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PromptSegment:
    """A single segment of the assembled system prompt."""
    key: str
    content: str
    enabled: bool = True
    priority: int = 0


class PromptAssemblyBuilder:
    """
    Chainable builder that composes a system prompt from discrete segments.

    Each segment is independently toggleable and debuggable.
    Segments are joined by double newlines in priority order (lower = higher priority, appears first).
    """

    def __init__(self):
        self._segments: list[PromptSegment] = []

    def add_section(
        self,
        key: str,
        content: str,
        *,
        enabled: bool = True,
        priority: int = 0,
    ) -> "PromptAssemblyBuilder":
        """Add a named prompt segment."""
        if not content or not content.strip():
            return self
        self._segments.append(
            PromptSegment(key=key, content=content.strip(), enabled=enabled, priority=priority)
        )
        return self

    def add_role(self, instruction: str) -> "PromptAssemblyBuilder":
        """Inject agent role / persona."""
        return self.add_section("role", instruction, priority=0)

    def add_skills_index(self, skills: list[dict]) -> "PromptAssemblyBuilder":
        """
        Inject a lightweight skill index (name + description only).
        The model uses the read_skill tool to fetch full SKILL.md on demand.
        """
        if not skills:
            return self
        lines = ["## Available Skills", ""]
        for s in skills:
            name = s.get("name", s.get("id", ""))
            desc = s.get("description", s.get("desc", ""))
            lines.append(f"- **{name}**: {desc}")
        lines.append("")
        lines.append("Use the `read_skill` tool to load the full instructions for any skill above.")
        return self.add_section("skills_index", "\n".join(lines), priority=10)

    def add_long_term_memory(self, memory_text: str) -> "PromptAssemblyBuilder":
        """Inject distilled long-term memory for this worker/agent."""
        if not memory_text or not memory_text.strip():
            return self
        return self.add_section("long_term_memory", memory_text, priority=20)

    def add_tools_schema(self, tools: list, mode: str = "names") -> "PromptAssemblyBuilder":
        """Inject available tool information."""
        if not tools:
            return self
        if mode == "names":
            names = [getattr(t, "name", str(t)) for t in tools]
            content = "## Available Tools\n\n" + "\n".join(f"- `{n}`" for n in names)
        else:
            content = "## Available Tools\n\n" + "\n".join(
                f"- `{getattr(t, 'name', str(t))}`: {getattr(t, 'description', '')}"
                for t in tools
            )
        return self.add_section("tools", content, priority=30)

    def disable(self, key: str) -> "PromptAssemblyBuilder":
        """Disable a specific segment by key."""
        for seg in self._segments:
            if seg.key == key:
                seg.enabled = False
        return self

    def enable(self, key: str) -> "PromptAssemblyBuilder":
        """Enable a specific segment by key."""
        for seg in self._segments:
            if seg.key == key:
                seg.enabled = True
        return self

    def build(self) -> str:
        """Assemble all enabled segments into the final prompt string."""
        active = [s for s in self._segments if s.enabled]
        active.sort(key=lambda s: s.priority)
        parts = [s.content for s in active]
        result = "\n\n".join(parts)
        logger.debug(
            "[PromptAssembly] Built prompt: %d segments active, %d chars total. Segments: %s",
            len(active),
            len(result),
            [s.key for s in active],
        )
        return result

    def debug_info(self) -> dict:
        """Return diagnostic info about the current segment state."""
        return {
            "total_segments": len(self._segments),
            "active_segments": [s.key for s in self._segments if s.enabled],
            "disabled_segments": [s.key for s in self._segments if not s.enabled],
            "segment_sizes": {s.key: len(s.content) for s in self._segments if s.enabled},
        }
