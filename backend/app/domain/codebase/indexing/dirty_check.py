"""Standalone dirty-check utility extracted from FilePreparer.

The mtime + checksum logic is promoted here so callers such as
``_run_semantic_extraction``, ``StandardsAnalyst`` and ``ProjectClassifier``
can avoid re-processing files whose content has not changed since last index.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.file import compute_md5
from app.models.codebase import SourceFile

logger = logging.getLogger(__name__)


async def is_file_changed_since_last_index(
    file_path: str,
    repo_id: int,
    session: AsyncSession,
    *,
    force: bool = False,
) -> bool:
    """Check whether *file_path* needs re-indexing.

    Uses the same two-tier dirty-check as ``FilePreparer.prepare()``:

    1. **mtime optimisation** – if the file's ``mtime`` is older than the
       stored ``last_indexed_at`` the file is considered unchanged.
    2. **checksum fallback** – when mtime is unavailable or newer, the file
       content is hashed (MD5) and compared to the stored checksum.

    Args:
        file_path: Absolute path to the file on disk.
        repo_id: Repository (primary key, not project id) the file belongs to.
        session: Open database session.
        force: When ``True``, the file is always considered changed.

    Returns:
        ``True`` if the file should be re-indexed, ``False`` if unchanged.
    """
    if force:
        return True

    root_path = _resolve_repo_path(repo_id)
    if not root_path:
        return True

    rel_path = os.path.relpath(file_path, root_path)

    stmt = select(SourceFile).where(
        SourceFile.repository_id == repo_id,
        SourceFile.path == rel_path,
    )
    result = await session.execute(stmt)
    source_file = result.scalars().first()
    if source_file is None:
        return True

    # mtime optimisation
    try:
        mtime_ts = os.path.getmtime(file_path)
        file_mtime = datetime.fromtimestamp(mtime_ts, timezone.utc)
        if source_file.last_indexed_at and file_mtime < source_file.last_indexed_at:
            return False
    except (OSError, ValueError, OverflowError):
        logger.debug("[dirty_check] mtime check failed, falling back to checksum", exc_info=True)

    # Checksum comparison – only read & hash when mtime didn't settle it.
    try:
        with open(file_path, "rb") as f:
            content = f.read()
        new_checksum = compute_md5(content)
    except Exception as e:
        logger.warning("[DirtyCheck] Could not read/hash %s: %s", file_path, e)
        return True

    if source_file.checksum == new_checksum:
        return False

    return True


def _resolve_repo_path(repo_id: int) -> str | None:
    """Resolve the repository's local path synchronously.

    This is a lightweight sync helper so the function can be used in contexts
    where an async ORM load is undesirable (e.g. startup).  For full-fledged
    resolution, callers should load the ``Repository`` themselves and pass the
    root path as an additional argument.
    """
    from sqlmodel import Session as SyncSession

    from app.infrastructure.database.resource_manager import (
        db_resource_manager as rm,
    )

    try:
        with SyncSession(rm.sync_engine) as session:
            from app.models.codebase import Repository

            repo = session.get(Repository, repo_id)
            if repo is None:
                return None
            return repo.local_path
    except Exception as e:
        logger.warning("[DirtyCheck] Failed to resolve repo path: %s", e)
        return None
