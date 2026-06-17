import asyncio
import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.evocloud import evocloud_manager
from app.core.file import get_file_ext
from app.core.project.utils import get_project_path
from app.domain.codebase.indexing.components.content_indexer import ContentIndexer
from app.domain.codebase.indexing.components.file_preparer import FilePreparer
from app.domain.codebase.indexing.components.graph_syncer import GraphSyncer
from app.domain.codebase.indexing.components.sql_persister import SQLPersister
from app.domain.codebase.indexing.extractors.treesitter_extractor import (
    TreeSitterExtractor,
)
from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.embeddings.base import BaseEmbedder
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.models import (
    Repository,
    SourceFile,
)

logger = logging.getLogger(__name__)


class IndexingService:
    """
    Orchestrates the file indexing pipeline using specialized components.

    Components:
    - FilePreparer: File filtering, reading, validation
    - ContentIndexer: Code extraction, embedding generation
    - SQLPersister: SQL database persistence
    - GraphSyncer: Neo4j graph synchronization
    """

    def __init__(self, session: AsyncSession = None):
        self.session_factory = session_scope

        # Legacy references (for backward compatibility)
        self.extractor = TreeSitterExtractor()
        self.embedder: BaseEmbedder = EmbedderFactory.get_embedder()

        # New component-based architecture
        self.file_preparer = FilePreparer()
        self.content_indexer = ContentIndexer(self.extractor, self.embedder)
        self.sql_persister = SQLPersister()
        self.graph_syncer = GraphSyncer()

    async def get_repo_by_path(self, path: str) -> Repository | None:
        """
        Look up a repository by its local path.
        """
        async with self.session_factory() as session:
            stmt = select(Repository).where(Repository.local_path == path)
            result = await session.execute(stmt)
            return result.scalars().first()

    async def get_or_create_repo(
        self, path: str, name: str, project_id: int = None
    ) -> Repository:
        async with self.session_factory() as session:
            # Check existing
            stmt = select(Repository).where(Repository.local_path == path)
            result = await session.execute(stmt)
            repo = result.scalars().first()

            if repo:
                return repo

            # Resolve Project ID dynamically (if not provided)
            # Default to None (Pending) if resolution fails, supporting Offline Mode.
            resolved_pid = project_id
            sync_status = "SYNCED"

            if not resolved_pid:
                try:
                    projects = await evocloud_manager.scan_projects()
                    abs_path = os.path.abspath(path)
                    for p in projects:
                        if p.get("path") and os.path.abspath(p.get("path")) == abs_path:
                            resolved_pid = p.get("id")
                            break
                except Exception as e:
                    logger.warning(f"Failed to resolve project_id for {path}: {e}")

            if not resolved_pid:
                sync_status = "PENDING_CREATION"

            # Create Repo
            repo = Repository(
                project_id=resolved_pid,
                name=name,
                url="local",
                local_path=path,
                sync_status=sync_status,
            )
            session.add(repo)
            await session.commit()
            await session.refresh(repo)
            return repo

    async def get_all_repos(self) -> list[Repository]:
        """
        Get all repositories from the database.
        """
        async with self.session_factory() as session:
            stmt = select(Repository)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def _resolve_project_path(self, repo: Repository) -> str | None:
        """Resolve local project path for a repository via project_id lookup."""
        if repo.project_id is not None:
            resolved = await get_project_path(repo.project_id)
            if resolved and os.path.isdir(resolved):
                return resolved
        if repo.local_path and os.path.isdir(repo.local_path):
            return repo.local_path
        return None

    async def index_file(self, file_path: str, repo_id: int, force: bool = False):
        """
        Index a single file using the component-based pipeline.
        """
        logger.info(f"[index_file] Enter: {file_path} repo_id={repo_id}")
        async with self.session_factory() as session:
            try:
                repo = await session.get(Repository, repo_id)
                if not repo:
                    logger.error(f"Repository {repo_id} not found")
                    return

                repo_path = await self._resolve_project_path(repo)
                if not repo_path:
                    logger.warning(
                        f"[index_file] No resolvable project path for repo {repo_id}. Skipping {file_path}."
                    )
                    return

                # 1. Prepare
                prepared = await self.file_preparer.prepare(
                    file_path, repo, session, force=force, repo_path=repo_path
                )
                if not prepared:
                    return

                # 2. Index Content
                indexed = await self.content_indexer.index(
                    file_path, prepared.content, prepared.rel_path
                )
                if not indexed:
                    # Safe Indexing: Skip wiping database to preserve "Last Known Good"
                    # This happens for substantial files (>50 chars) where extraction fails.
                    return

                # 3. Persist SQL
                source_file = await self.file_preparer.create_or_update_source_file(
                    prepared, session
                )
                await self.sql_persister.clear_old_data(source_file, session)
                name_to_id = await self.sql_persister.persist(
                    indexed, source_file, session
                )

                # 3.5 Persist vectors to unified vector store (skip if no embeddings generated)
                if indexed.embeddings:
                    from app.infrastructure.database.vector import get_vector_store

                    vector_store = get_vector_store(project_path=repo_path)
                    chunks_for_vec = []
                    for doc in indexed.documents:
                        chunks_for_vec.append(
                            {
                                "content": doc.content,
                                "file_path": prepared.rel_path,
                                "repository_id": str(repo_id),
                                "chunk_type": doc.metadata.get("type", "unknown"),
                                "identifier": doc.metadata.get("name", "unknown"),
                                "start_line": doc.metadata.get("start_line", 0),
                                "end_line": doc.metadata.get("end_line", 0),
                                "language": get_file_ext(prepared.file_path),
                            }
                        )
                    # Run synchronous vector store I/O in a thread to avoid blocking
                    # the event loop (especially for PgVectorStore network calls).
                    await asyncio.to_thread(
                        vector_store.upsert_code_chunks,
                        chunks_for_vec,
                        indexed.embeddings,
                    )
                else:
                    logger.warning(
                        f"Skipping vector upsert for {prepared.rel_path}: No embeddings generated (provider might be unconfigured)."
                    )

                # 4. Sync Graph
                try:
                    line_count = prepared.content.count("\n") + 1
                    await self.graph_syncer.sync(
                        prepared,
                        indexed,
                        line_count,
                        source_file_pg_id=source_file.id,
                        entity_pg_ids=name_to_id,
                        repo_path=repo_path,
                    )
                except NotImplementedError:
                    logger.debug(
                        "[IndexingService] Graph sync skipped (not supported in embedded mode)"
                    )

            except Exception as e:
                logger.error(f"Error indexing file {file_path}: {e}")
                await session.rollback()

    async def remove_file(self, file_path: str, repo_id: int):
        """
        Handle file deletion.
        """
        async with self.session_factory() as session:
            try:
                repo = await session.get(Repository, repo_id)
                if not repo:
                    return

                repo_path = await self._resolve_project_path(repo)
                if not repo_path:
                    logger.warning(
                        f"[remove_file] No resolvable project path for repo {repo_id}. Skipping {file_path}."
                    )
                    return

                rel_path = os.path.relpath(file_path, repo_path)

                # 1. SQL Cleanup
                stmt = select(SourceFile).where(
                    SourceFile.repository_id == repo_id, SourceFile.path == rel_path
                )
                result = await session.execute(stmt)
                source_file = result.scalars().first()

                if source_file:
                    await self.sql_persister.clear_old_data(source_file, session)
                    await session.delete(source_file)
                    logger.info(f"Removed {rel_path} from SQL Index")

                # 2. Graph Cleanup
                try:
                    driver = await get_graph_db(project_path=repo_path)
                    project_id = repo.project_id

                    # 1. Delete associated Entities (CONTAINS)
                    # Note: Our delete_nodes is simpler, it deletes nodes of a label matching filters.
                    # To mimic the DETACH DELETE of entities contained in f, we find them or just delete by project_id/rel_path if they were tagged.
                    # Actually, our CodeEntity nodes have full_name.
                    # For simplicity and robustness, we can delete entities that might be orphaned.
                    # But the current IGraphDriver.delete_nodes doesn't support complex joins.

                    # Fallback: Use execute_query but route it through driver
                    await driver.execute_query(
                        """
                        MATCH (f:File {path: $path, project_id: $pid})
                        OPTIONAL MATCH (f)-[:CONTAINS]->(e)
                        DETACH DELETE e
                        DETACH DELETE f
                        """,
                        path=rel_path,
                        pid=project_id,
                    )
                    logger.info(f"Removed {rel_path} from Graph Index")
                except NotImplementedError:
                    logger.debug(
                        "[IndexingService] Graph cleanup skipped (not supported in embedded mode)"
                    )
                except Exception as e:
                    logger.warning(
                        f"[IndexingService] Graph cleanup failed for {rel_path}: {e}"
                    )

            except Exception as e:
                logger.error(f"Error removing file {file_path}: {e}")
                await session.rollback()

    async def move_file(self, src_path: str, dest_path: str, repo_id: int):
        """
        Handle file move/rename.
        Treat as Remove + Index to ensure full graph identity regeneration.
        """
        # 1. Remove Old
        await self.remove_file(src_path, repo_id)

        # 2. Index New
        # Ensure new path exists logic is handled by caller or index_file just reads it.
        # If this is triggered by Watcher, file already exists at dest_path.
        if os.path.exists(dest_path):
            await self.index_file(dest_path, repo_id)
            logger.info(f"Moved (Re-indexed) {src_path} -> {dest_path}")
        else:
            logger.warning(f"Move Error: Dest {dest_path} not found.")

    async def index_repository(self, repo_path: str, repo_id: int, force: bool = False):
        """
        Main entry point to index a repository on disk.
        """
        if not repo_path or not os.path.isdir(repo_path):
            logger.warning(
                f"[index_repository] Skipping repo {repo_id}: invalid path {repo_path}"
            )
            return

        logger.info(
            f"Starting full indexing for repo {repo_id} at {repo_path} (Force={force})"
        )

        from app.constants import BLACKLIST_DIRS
        from app.core.file.service import walk_tree
        from app.domain.codebase.ignore import GitignoreMatcher

        ignore_matcher = GitignoreMatcher.from_file(repo_path, ".gitignore")

        def dir_filter(d_path: str) -> bool:
            return not ignore_matcher.should_ignore(d_path, is_dir=True)

        def file_check(f_path: str) -> bool:
            if ignore_matcher.should_ignore(f_path, is_dir=False):
                return False
            return self.file_preparer.should_index(f_path)

        # Walk directory (offloaded to thread to avoid blocking the event loop)
        filtered_files = await asyncio.to_thread(
            lambda: list(
                walk_tree(
                    repo_path,
                    filter_func=file_check,
                    dir_filter=dir_filter,
                    exclude_dirs=BLACKLIST_DIRS,
                )
            )
        )

        logger.info(
            f"Found {len(filtered_files)} valid files to index (Applied .gitignore)."
        )

        # Concurrent indexing with bounded parallelism. In embedded mode the
        # SQLite backend and the shared local embedder do not scale with high
        # fan-out. We use a very small semaphore to avoid SQLite/vector-store
        # lock contention while still making some progress.
        CONCURRENT_FILES = 2
        _index_semaphore = asyncio.Semaphore(CONCURRENT_FILES)
        total_files = len(filtered_files)
        indexed_count = 0
        error_count = 0

        async def _index_one(file_path: str) -> None:
            async with _index_semaphore:
                await self.index_file(file_path, repo_id, force=force)

        for i in range(0, total_files, CONCURRENT_FILES):
            batch = filtered_files[i : i + CONCURRENT_FILES]

            # Create tasks for concurrent execution
            tasks = [_index_one(f) for f in batch]

            # Execute batch concurrently, capture exceptions
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    error_count += 1
                    logger.error(f"Failed to index {batch[idx]}: {result}")
                else:
                    indexed_count += 1

            # Progress logging
            progress = min(i + CONCURRENT_FILES, total_files)
            logger.info(
                f"Progress: {progress}/{total_files} files ({indexed_count} success, {error_count} errors)"
            )

        logger.info(
            f"Full indexing complete. Indexed: {indexed_count}, Errors: {error_count}"
        )
