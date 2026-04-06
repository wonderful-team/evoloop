"""
Memory System Data Models

Unified memory data models for both embedded and full modes.
Inspired by Claude Code's memory type taxonomy.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
import json


class MemoryType(str, Enum):
    """
    Four-type memory taxonomy (inspired by Claude Code).
    
    Memories are constrained to these types capturing context NOT derivable
    from the current project state.
    """
    USER = "user"
    """User's role, goals, expertise, and preferences. Always private."""
    
    FEEDBACK = "feedback"
    """Guidance on what to do/avoid. Default private, can be team if project-wide convention."""
    
    PROJECT = "project"
    """Project context, decisions, milestones. Team scope preferred."""
    
    REFERENCE = "reference"
    """External system pointers. Usually team scope."""


class PrivacyLevel(str, Enum):
    """Privacy scope for memory entries."""
    PRIVATE = "private"
    """Only visible to current user."""
    
    TEAM = "team"
    """Shared with team members."""


@dataclass
class MemoryEntry:
    """
    Unified memory entry model.
    
    Replaces Concept and Episode with a more flexible, file-based model
    inspired by Claude Code's memory files.
    """
    
    # Identity
    id: str
    """Unique identifier (e.g., 'mem_user_001', 'mem_proj_042')"""
    
    # Classification
    type: MemoryType
    """Memory type from the four-type taxonomy."""
    
    privacy: PrivacyLevel
    """Privacy scope (default determined by type)."""
    
    # Content
    title: str
    """Short title for indexing and display."""
    
    content: str
    """Markdown content (can be multi-line with headers, lists, etc.)"""
    
    description: str = ""
    """One-line description for search results and summaries."""
    
    # Metadata
    project_id: Optional[int] = None
    """Associated project ID (None for global memories)."""
    
    user_id: Optional[str] = None
    """Owner user ID (for private memories)."""
    
    tags: List[str] = field(default_factory=list)
    """Tags for categorization and filtering."""
    
    # Source tracking
    source: str = "manual"
    """Source of the memory: 'manual', 'extracted', 'consolidated', 'imported'"""
    
    source_message_id: Optional[str] = None
    """Original message ID if extracted from conversation."""
    
    confidence: float = 1.0
    """Confidence score (0.0-1.0), primarily for extracted memories."""
    
    # Versioning
    version: int = 1
    """Version number for optimistic locking."""
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    """Creation timestamp."""
    
    updated_at: datetime = field(default_factory=datetime.utcnow)
    """Last update timestamp."""
    
    # Additional metadata
    extra: dict = field(default_factory=dict)
    """Additional type-specific metadata."""
    
    def __post_init__(self):
        """Set default privacy based on type if not specified."""
        if isinstance(self.type, str):
            self.type = MemoryType(self.type)
        if isinstance(self.privacy, str):
            self.privacy = PrivacyLevel(self.privacy)
    
    def to_frontmatter(self) -> str:
        """
        Serialize to Markdown with YAML frontmatter.
        
        Format compatible with Claude Code memory files:
        ---
        id: "..."
        type: "..."
        ...
        ---
        
        # Content
        ...
        """
        import yaml
        
        # Clean strings to ensure valid YAML (aggressive sanitization)
        def _clean_yaml_string(s: str, max_len: int) -> str:
            if not s:
                return ""
            # Replace newlines and carriage returns with space
            s = s.replace('\n', ' ').replace('\r', ' ')
            # Remove all YAML special/reserved characters
            # | > ' " # & * ! ? | - : { } [ ] , 
            yaml_special = '|>#&*!?-:{}[],'
            for char in yaml_special:
                s = s.replace(char, ' ')
            # Collapse multiple spaces to single space
            s = ' '.join(s.split())
            # Strip and limit length
            return s.strip()[:max_len]
        
        clean_title = _clean_yaml_string(self.title, 80)
        clean_description = _clean_yaml_string(self.description, 150)
        
        frontmatter = {
            "id": self.id,
            "type": self.type.value,
            "privacy": self.privacy.value,
            "title": clean_title,
            "description": clean_description,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "tags": self.tags,
            "source": self.source,
            "source_message_id": self.source_message_id,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        
        # Add extra metadata if present
        if self.extra:
            frontmatter["extra"] = self.extra
        
        # Use PyYAML for proper serialization (handles newlines, special chars, etc.)
        yaml_content = yaml.safe_dump(
            frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,  # Preserve key order
        )
        
        # Wrap in frontmatter delimiters
        frontmatter_text = f"---\n{yaml_content}---"
        
        # Combine with content
        return frontmatter_text + "\n\n" + self.content
    
    @classmethod
    def from_frontmatter(cls, text: str, file_path: Optional[str] = None) -> "MemoryEntry":
        """
        Parse from Markdown with YAML frontmatter.
        
        Args:
            text: The markdown text to parse
            file_path: Optional file path for error reporting
            
        Returns:
            MemoryEntry instance
        """
        import yaml
        
        # Split frontmatter and content
        if not text.startswith("---"):
            # No frontmatter - treat entire text as content
            # Try to infer from file path
            return cls._from_content_only(text, file_path)
        
        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid frontmatter format in {file_path or 'unknown'}")
        
        # Parse YAML frontmatter
        try:
            frontmatter = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML frontmatter in {file_path or 'unknown'}: {e}")
        
        if not isinstance(frontmatter, dict):
            raise ValueError(f"Frontmatter must be a dict in {file_path or 'unknown'}")
        
        # Extract content (everything after second ---)
        content = parts[2].strip()
        
        # Parse timestamps
        created_at = cls._parse_timestamp(frontmatter.get("created_at"))
        updated_at = cls._parse_timestamp(frontmatter.get("updated_at"))
        
        return cls(
            id=frontmatter.get("id", ""),
            type=MemoryType(frontmatter.get("type", "project")),
            privacy=PrivacyLevel(frontmatter.get("privacy", "private")),
            title=frontmatter.get("title", ""),
            content=content,
            description=frontmatter.get("description", ""),
            project_id=frontmatter.get("project_id"),
            user_id=frontmatter.get("user_id"),
            tags=frontmatter.get("tags", []),
            source=frontmatter.get("source", "manual"),
            source_message_id=frontmatter.get("source_message_id"),
            confidence=frontmatter.get("confidence", 1.0),
            version=frontmatter.get("version", 1),
            created_at=created_at,
            updated_at=updated_at,
            extra=frontmatter.get("extra", {}),
        )
    
    @classmethod
    def _from_content_only(cls, text: str, file_path: Optional[str] = None) -> "MemoryEntry":
        """Create entry from content only (infer metadata from path)."""
        import uuid
        
        # Try to infer type from path
        mem_type = MemoryType.PROJECT
        privacy = PrivacyLevel.PRIVATE
        
        if file_path:
            path_lower = file_path.lower()
            if "/private/" in path_lower or "\\private\\" in path_lower:
                privacy = PrivacyLevel.PRIVATE
            elif "/team/" in path_lower or "\\team\\" in path_lower:
                privacy = PrivacyLevel.TEAM
            
            if "/user" in path_lower or "\\user" in path_lower:
                mem_type = MemoryType.USER
            elif "/feedback" in path_lower or "\\feedback" in path_lower:
                mem_type = MemoryType.FEEDBACK
            elif "/reference" in path_lower or "\\reference" in path_lower:
                mem_type = MemoryType.REFERENCE
        
        # Use first line as title
        lines = text.strip().split("\n")
        title = lines[0][:100] if lines else "Untitled"
        
        return cls(
            id=f"mem_imported_{uuid.uuid4().hex[:8]}",
            type=mem_type,
            privacy=privacy,
            title=title,
            content=text,
            description=title[:200],
            source="imported",
        )
    
    @staticmethod
    def _parse_timestamp(ts: Any) -> datetime:
        """Parse timestamp from various formats."""
        if ts is None:
            return datetime.utcnow()
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            # Try ISO format
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.utcnow()
    
    def to_search_result(self) -> "MemorySearchResult":
        """Convert to search result (without full content)."""
        return MemorySearchResult(
            id=self.id,
            type=self.type,
            title=self.title,
            description=self.description,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


@dataclass
class MemorySearchResult:
    """Lightweight result for search operations (without full content)."""
    
    id: str
    type: MemoryType
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class MemoryIndexEntry:
    """
    Entry in MEMORY.md index file.
    
    Format: `- [Title](path/to/file.md) — description`
    """
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
        
        # Match: - [Title](path) — description
        # or: - [Title](path)
        pattern = r"^- \[([^\]]+)\]\(([^)]+)\)(?:\s*—\s*(.+))?"
        match = re.match(pattern, line.strip())
        
        if match:
            return cls(
                title=match.group(1),
                path=match.group(2),
                description=match.group(3) or "",
            )
        return None
