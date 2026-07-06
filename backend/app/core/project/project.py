"""
Project — unified value object for the project domain.

A "Project" has four representations in the codebase:
  1. Repository (DB ORM) — persistence layer
  2. .evoloop/project.json — local truth on disk
  3. LocalProjectEntry — filesystem scan result
  4. EvoCloud dict — cloud view

This value object unifies the common fields so callers don't have to
juggle project_id / repo_id / path / name / sync_status separately.

Usage:
    from app.core.project.project import Project

    proj = Project.from_local_entry(entry)
    print(proj.path, proj.project_id, proj.name)

    proj = Project.from_repo(repo_orm)
    print(proj.sync_status, proj.repo_id)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.project.local_index import LocalProjectEntry
    from app.models.codebase import Repository


@dataclass(frozen=True)
class Project:
    """Unified project value object.

    Immutable by design — callers construct a fresh instance when
    state changes (e.g. after cloud sync updates sync_status).
    """

    project_id: int | None = None
    repo_id: int | None = None
    path: str | None = None
    name: str | None = None
    sync_status: str = "DETECTED"
    member_id: int = 0
    cloud_project_id: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    # --- Factories ---

    @classmethod
    def from_local_entry(cls, entry: "LocalProjectEntry") -> "Project":
        """Construct from a LocalProjectEntry (filesystem scan result)."""
        return cls(
            project_id=entry.project_id,
            repo_id=entry.repo_id,
            path=entry.path,
            name=entry.name,
        )

    @classmethod
    def from_repo(cls, repo: "Repository") -> "Project":
        """Construct from a Repository DB ORM row."""
        return cls(
            project_id=repo.project_id,
            repo_id=repo.id,
            path=repo.local_path,
            name=repo.name,
            sync_status=repo.sync_status,
            member_id=repo.member_id,
        )

    @classmethod
    def from_cloud_dict(cls, data: dict[str, Any]) -> "Project":
        """Construct from an EvoCloud project dict."""
        return cls(
            project_id=data.get("project_id"),
            cloud_project_id=data.get("project_id"),
            path=data.get("external_path"),
            name=data.get("name"),
            sync_status="SYNCED" if data.get("project_id") else "DETECTED",
            extra={k: v for k, v in data.items() if k not in ("project_id", "external_path", "name")},
        )

    # --- Predicates ---

    @property
    def is_synced(self) -> bool:
        return self.sync_status == "SYNCED"

    @property
    def is_ignored(self) -> bool:
        return self.sync_status == "IGNORED"

    @property
    def is_detected(self) -> bool:
        return self.sync_status == "DETECTED"

    @property
    def is_disconnected(self) -> bool:
        return self.sync_status == "DISCONNECTED"

    @property
    def has_cloud(self) -> bool:
        return self.cloud_project_id is not None or self.project_id is not None

    def __fspath__(self) -> str:
        """Support os.path functions — returns the local path."""
        return self.path or ""
