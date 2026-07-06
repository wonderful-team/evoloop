import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.file import compute_md5, get_file_ext
from app.core.file.document_reader import document_reader_service
from app.domain.codebase.filter import FileFilter
from app.domain.codebase.schemas import PreparedFile
from app.models import Repository, SourceFile

logger = logging.getLogger(__name__)


class FilePreparer:
    """
    Prepares files for indexing by:
    - Filtering (using FileFilter)
    - Extension validation (using ParserRegistry)
    - Reading content
    - Computing checksum
    - Checking if file needs re-indexing
    """

    def __init__(self):
        self.file_filter = FileFilter()

    def should_index(self, file_path: str) -> bool:
        """Check if file should be indexed (filter + extension check)."""
        from app.constants import INDEXABLE_EXTENSIONS

        if not self.file_filter.should_include(file_path):
            return False

        ext = get_file_ext(file_path)
        return ext in INDEXABLE_EXTENSIONS

    async def prepare(
        self,
        file_path: str,
        repo: Repository,
        session: AsyncSession,
        force: bool = False,
        repo_path: str | None = None,
    ) -> PreparedFile | None:
        """
        Prepare a file for indexing.

        Args:
            repo_path: Optional resolved project root. If not provided, falls back
                       to repo.local_path for backwards compatibility.

        Returns:
            PreparedFile if the file needs indexing, None if it should be skipped.
        """
        # Filter check
        if not self.should_index(file_path):
            return None

        root_path = repo_path if repo_path else repo.local_path
        if not root_path:
            logger.warning(
                f"[FilePreparer] No project root available for repo {repo.id}"
            )
            return None

        rel_path = os.path.relpath(file_path, root_path)

        # Check existing SourceFile
        stmt = select(SourceFile).where(
            SourceFile.repository_id == repo.id, SourceFile.path == rel_path
        )
        result = await session.execute(stmt)
        source_file = result.scalars().first()

        # mtime optimization
        if not force and source_file:
            try:
                mtime_ts = os.path.getmtime(file_path)
                file_mtime = datetime.fromtimestamp(mtime_ts, timezone.utc)
                if (
                    source_file.last_indexed_at
                    and file_mtime < source_file.last_indexed_at
                ):
                    return None  # File unchanged
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                pass  # Fallback to checksum

        # Read content
        try:
            content = await document_reader_service.read_document(file_path)
            if content is None:
                return None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return None

        # Checksum
        new_checksum = compute_md5(content)

        # Check if content changed
        if not force and source_file and source_file.checksum == new_checksum:
            # Update timestamp to avoid future mtime checks
            source_file.last_indexed_at = datetime.now(timezone.utc)
            session.add(source_file)
            await session.commit()
            return None

        logger.info(f"Indexing {rel_path} (Force={force}, Checksum mismatch or new)")

        return PreparedFile(
            file_path=file_path,
            rel_path=rel_path,
            content=content,
            checksum=new_checksum,
            source_file=source_file,
            is_new=source_file is None,
            repo=repo,
        )

    async def create_or_update_source_file(
        self, prepared: PreparedFile, session: AsyncSession
    ) -> SourceFile:
        """Create or update the SourceFile record."""
        if prepared.is_new:
            source_file = SourceFile(
                repository_id=prepared.repo.id,
                path=prepared.rel_path,
                checksum=prepared.checksum,
            )
            session.add(source_file)
            await session.flush()
        else:
            source_file = prepared.source_file
            source_file.checksum = prepared.checksum
            source_file.last_indexed_at = datetime.now(timezone.utc)
            session.add(source_file)
            await session.flush()

        return source_file
