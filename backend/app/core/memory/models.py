import hashlib
import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import yaml
from pydantic import Field, model_validator

from app.core.memory.schemas import MemoryMetadata
from app.infrastructure.pydantic_base import DynamicBaseModel


class MemoryType(str, Enum):
    """Four-type memory taxonomy (inspired by Claude Code)."""
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"
    CONCEPT = "concept"
    EPISODE = "episode"


class MemoryTier(str, Enum):
    """Quality-based tiering for memory management."""
    STRATEGIC = "strategic"
    OPERATIONAL = "operational"
    TRANSIENT = "transient"


class PrivacyLevel(str, Enum):
    """Privacy scope for memory entries."""
    PRIVATE = "private"
    TEAM = "team"


class MemoryEntry(DynamicBaseModel):
    """
    Unified memory entry model.
    Format compatible with Claude Code memory files (Markdown + YAML Frontmatter).
    """
    # Identity
    id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:8]}")

    # Classification
    type: MemoryType = MemoryType.PROJECT
    privacy: PrivacyLevel = PrivacyLevel.PRIVATE

    # Content & Fingerprint
    title: str
    content: str
    description: str = ""
    content_hash: str | None = None  # SHA-256 fingerprint for global de-dupe

    # Metadata
    project_id: int | None = None
    user_id: str | None = None
    tags: list[str] = Field(default_factory=list)

    # Source tracking
    source: str = "manual"
    source_message_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    # Versioning
    version: int = 1
    tier: MemoryTier = MemoryTier.OPERATIONAL
    utility_score: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional metadata
    extra: MemoryMetadata = Field(default_factory=MemoryMetadata)

    @model_validator(mode='before')
    @classmethod
    def set_default_privacy(cls, data: Any) -> Any:
        if isinstance(data, dict) and "privacy" not in data and "type" in data:
            mtype = data["type"]
            if mtype == MemoryType.USER:
                data["privacy"] = PrivacyLevel.PRIVATE
        return data

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """
        Compute a stable SHA-256 hash for memory content.
        Normalizes whitespace and case to ensure consistent fingerprinting.
        """
        if not content:
            return ""
        # Normalize: lower case, strip, replace complex whitespace with single space
        normalized = re.sub(r'\s+', ' ', content.strip().lower())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def to_frontmatter(self) -> str:
        """Serialize to Markdown with YAML frontmatter."""
        # Clean strings for YAML
        def _clean(s: str) -> str:
            return ' '.join((s or "").replace('\n', ' ').split()).strip()[:150]

        frontmatter = {
            "id": self.id,
            "type": self.type.value,
            "tier": self.tier.value,
            "utility_score": self.utility_score,
            "privacy": self.privacy.value,
            "title": _clean(self.title),
            "description": _clean(self.description),
            "project_id": self.project_id,
            "user_id": self.user_id,
            "tags": self.tags,
            "source": self.source,
            "source_message_id": self.source_message_id,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "content_hash": self.content_hash,
        }
        if self.extra:
            frontmatter["extra"] = self.extra.model_dump()

        yaml_content = yaml.safe_dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return f"---\n{yaml_content}---\n\n{self.content}"

    @classmethod
    def from_frontmatter(cls, text: str, file_path: str | None = None) -> "MemoryEntry":
        """Parse from Markdown with YAML frontmatter."""
        if not text.startswith("---"):
            return cls._from_content_only(text, file_path)

        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid frontmatter format in {file_path or 'unknown'}")

        try:
            frontmatter = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML frontmatter in {file_path or 'unknown'}: {e}")

        if not isinstance(frontmatter, dict):
            raise ValueError(f"Frontmatter must be a dict in {file_path or 'unknown'}")

        content = parts[2].strip()

        # Parse timestamps safely via Pydantic validator or manual
        data = {**frontmatter, "content": content}
        return cls.model_validate(data)

    @classmethod
    def _from_content_only(cls, text: str, file_path: str | None = None) -> "MemoryEntry":
        """Create entry from content only (infer metadata from path)."""
        mem_type = MemoryType.PROJECT
        privacy = PrivacyLevel.PRIVATE

        if file_path:
            path_lower = file_path.lower()
            if "/private/" in path_lower:
                privacy = PrivacyLevel.PRIVATE
            elif "/team/" in path_lower:
                privacy = PrivacyLevel.TEAM

            if "/user" in path_lower:
                mem_type = MemoryType.USER
            elif "/feedback" in path_lower:
                mem_type = MemoryType.FEEDBACK
            elif "/reference" in path_lower:
                mem_type = MemoryType.REFERENCE

        lines = text.strip().split("\n")
        title = lines[0][:100] if lines else "Untitled"

        return cls(
            type=mem_type,
            privacy=privacy,
            title=title,
            content=text,
            description=title[:200],
            source="imported"
        )

    def to_search_result(self) -> "MemorySearchResult":
        """Convert to search result (without full content)."""
        return MemorySearchResult(
            id=self.id,
            type=self.type,
            tier=self.tier,
            utility_score=self.utility_score,
            title=self.title,
            description=self.description,
            created_at=self.created_at,
            updated_at=self.updated_at,
            confidence=self.confidence,
        )


class MemorySearchResult(DynamicBaseModel):
    """Lightweight result for search operations (without full content)."""
    id: str
    type: MemoryType
    tier: MemoryTier = MemoryTier.OPERATIONAL
    utility_score: float = 0.0
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    confidence: float = 1.0

    def to_dict(self) -> dict:
        """Legacy compatibility method."""
        return self.model_dump()


class MemoryIndexEntry(DynamicBaseModel):
    """Entry in MEMORY.md index file."""
    title: str
    path: str
    description: str

    def to_index_line(self) -> str:
        """Format as index line."""
        if self.description:
            return f"- [{self.title}]({self.path}) — {self.description[:100]}"
        return f"- [{self.title}]({self.path})"

    @classmethod
    def from_index_line(cls, line: str) -> Optional["MemoryIndexEntry"]:
        """Parse from index line."""
        import re
        pattern = r"^- \[([^\]]+)\]\(([^)]+)\)(?:\s*—\s*(.+))?"
        match = re.match(pattern, line.strip())
        if match:
            return cls(title=match.group(1), path=match.group(2), description=match.group(3) or "")
        return None
