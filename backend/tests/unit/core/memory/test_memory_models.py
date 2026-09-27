"""Pure-logic unit tests for the memory models (no DB / disk / global init).

These cover the value-object / serialization layer that has no environment
dependencies, complementing the integration tests in
``tests/integration/test_memory_manager_facade.py``.
"""

from __future__ import annotations

from app.core.memory.models import (
    MemoryEntry,
    MemoryIndexEntry,
    MemoryType,
    PrivacyLevel,
)


def _entry() -> MemoryEntry:
    return MemoryEntry(
        id="concept_demo",
        type=MemoryType.CONCEPT,
        privacy=PrivacyLevel.TEAM,
        title="Demo Concept",
        description="A demo description",
        content="full body content here",
        project_id=1,
        member_id=0,
        memory_kind="concept",
        tags=["concept", "demo"],
    )


class TestContentHash:
    def test_normalizes_whitespace_and_case(self) -> None:
        h1 = MemoryEntry.compute_content_hash("  Hello   World  ")
        h2 = MemoryEntry.compute_content_hash("hello world")
        assert h1 == h2
        assert h1 != ""

    def test_empty_content_returns_empty(self) -> None:
        assert MemoryEntry.compute_content_hash("") == ""
        assert MemoryEntry.compute_content_hash(None) == ""


class TestFrontmatterRoundTrip:
    def test_to_frontmatter_contains_metadata(self) -> None:
        text = _entry().to_frontmatter()
        assert text.startswith("---\n")
        assert "type: concept" in text
        assert "privacy: team" in text
        assert "Demo Concept" in text

    def test_from_frontmatter_round_trips(self) -> None:
        entry = _entry()
        parsed = MemoryEntry.from_frontmatter(entry.to_frontmatter())
        assert parsed.id == entry.id
        assert parsed.title == entry.title
        assert parsed.type == MemoryType.CONCEPT
        assert parsed.content == "full body content here"


class TestIndexLine:
    def test_index_line_round_trip(self) -> None:
        idx = MemoryIndexEntry(title="X", path="/tmp/x.md", description="a note")
        line = idx.to_index_line()
        parsed = MemoryIndexEntry.from_index_line(line)
        assert parsed is not None
        assert parsed.title == "X"
        assert parsed.path == "/tmp/x.md"
        assert parsed.description == "a note"

    def test_index_line_without_description(self) -> None:
        idx = MemoryIndexEntry(title="X", path="/tmp/x.md", description="")
        assert idx.to_index_line() == "- [X](/tmp/x.md)"

    def test_malformed_index_line_returns_none(self) -> None:
        assert MemoryIndexEntry.from_index_line("not a valid line") is None


class TestMemoryEntryDefaults:
    def test_default_privacy_applied(self) -> None:
        entry = MemoryEntry(title="T", content="c")
        # Privacy and tier should have sane defaults, never None.
        assert entry.privacy is not None
        assert entry.tier is not None
        assert entry.type is MemoryType.PROJECT

    def test_user_type_forces_private_privacy(self) -> None:
        entry = MemoryEntry(title="T", content="c", type=MemoryType.USER)
        assert entry.privacy is PrivacyLevel.PRIVATE
