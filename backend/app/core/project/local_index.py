"""
Local project index: scans WORKSPACE_ROOT subdirectories for .evoloop/project.json
to build an authoritative project_id -> local_path mapping.

No TTL caching: the scan only reads direct subdirectories and one small JSON file
per project, so the overhead on local SSD is negligible. Simpler and safer.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from app.core.file import FileStatus, read_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocalProjectEntry:
    """A single local project mapping discovered from .evoloop/project.json."""

    path: str
    project_id: int
    repo_id: int | None = None
    name: str | None = None

    def __fspath__(self) -> str:
        """Support os.path / pathlib operations."""
        return self.path


class LocalProjectIndex:
    """
    Maintains a live project_id -> local_path index by scanning
    WORKSPACE_ROOT/{dir}/.evoloop/project.json files.

    Design choices:
    - Scan only direct children of WORKSPACE_ROOT.
    - No caching/TTL; rebuild the index on every access to avoid stale data.
    - On project_id conflicts, log a warning but never mutate project files.
      The caller (e.g. ProjectSyncService) is responsible for reconciliation.
    """

    def __init__(self):
        self._id_to_entry: dict[int, LocalProjectEntry] = {}
        self._path_to_id: dict[str, int] = {}

    def _read_project_meta(self, meta_path: str) -> dict | None:
        """Read and parse a project.json file. Return None on any error."""
        result = read_file(meta_path)
        if result.status != FileStatus.SUCCESS:
            return None
        try:
            return json.loads(result.content) or None
        except json.JSONDecodeError as e:
            logger.warning(f"[LocalProjectIndex] Invalid JSON at {meta_path}: {e}")
            return None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[LocalProjectIndex] Failed to read {meta_path}: {e}")
            return None

    def _coerce_repo_id(self, value: Any) -> int | None:
        """Coerce a repo_id value from project.json to int or None."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def refresh(self, workspace_root: str) -> dict[int, LocalProjectEntry]:
        """
        Synchronously scan workspace_root and rebuild the index recursively.

        Returns the rebuilt id -> entry mapping.
        """
        self._id_to_entry.clear()
        self._path_to_id.clear()

        if not workspace_root or not os.path.isdir(workspace_root):
            return {}

        from app.core.file import FileTraverser, is_ignored_path

        def scan_dir(current_dir: str, depth: int):
            if depth > 3:  # limit depth to 3 layers
                return
            if is_ignored_path(current_dir):
                return

            # Check if this directory itself is a project
            meta_file = os.path.join(current_dir, ".evoloop", "project.json")
            if os.path.exists(meta_file):
                meta = self._read_project_meta(meta_file)
                if meta:
                    project_id = meta.get("project_id")
                    if isinstance(project_id, int):
                        if project_id in self._id_to_entry:
                            existing = self._id_to_entry[project_id]
                            logger.warning(
                                f"[LocalProjectIndex] project_id {project_id} conflict: "
                                f"found at {existing.path} and {current_dir}; "
                                "keeping first discovered, please reconcile manually"
                            )
                        else:
                            repo_id = self._coerce_repo_id(meta.get("repo_id"))
                            local_entry = LocalProjectEntry(
                                path=current_dir,
                                project_id=project_id,
                                repo_id=repo_id,
                                name=meta.get("name"),
                            )
                            self._id_to_entry[project_id] = local_entry
                            self._path_to_id[current_dir] = project_id
                            # Stop scanning subdirectories of this project
                            return

            # If not a project, scan subdirectories
            try:
                entries = list(FileTraverser.list_entries(current_dir))
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"[LocalProjectIndex] Failed to list {current_dir}: {e}")
                return

            for entry in entries:
                sub_path = str(entry.path)
                if entry.is_dir():
                    scan_dir(sub_path, depth + 1)

        scan_dir(os.path.abspath(workspace_root), 0)
        return dict(self._id_to_entry)

    def get_entry(self, project_id: int, workspace_root: str) -> LocalProjectEntry | None:
        """Return the local project entry for a project_id, or None if not found."""
        self.refresh(workspace_root)
        return self._id_to_entry.get(project_id)

    def get_path(self, project_id: int, workspace_root: str) -> str | None:
        """Return the local absolute path for a project_id, or None if not found."""
        entry = self.get_entry(project_id, workspace_root)
        return entry.path if entry else None

    def get_project_id(self, path: str, workspace_root: str) -> int | None:
        """Return project_id for a given local absolute path, or None."""
        self.refresh(workspace_root)
        return self._path_to_id.get(os.path.abspath(path))


# Global instance
local_project_index = LocalProjectIndex()
