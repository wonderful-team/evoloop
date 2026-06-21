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
from app.domain.codebase.indexing.extractors.treesitter_extractor import TreeSitterExtractor
from app.domain.codebase.schemas import IndexedContent, PreparedFile
from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.embeddings.base import BaseEmbedder
from app.infrastructure.embeddings.batched import BatchedEmbedder
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

    async def index_file(
        self,
        file_path: str,
        repo_id: int,
        force: bool = False,
        *,
        prepared_override: PreparedFile | None = None,
        indexed_override: IndexedContent | None = None,
        content_indexer: ContentIndexer | None = None,
    ):
        """
        Index a single file using the component-based pipeline.

        Args:
            prepared_override: Optional pre-prepared file metadata. If provided,
                the prepare step is skipped and this value is used. Caller must
                provide a session that already contains this record.
            indexed_override: Optional pre-indexed content. If provided, content
                extraction/embedding is skipped. Useful for batched embedding
                scenarios.
            content_indexer: Optional ContentIndexer to use for extraction and
                embedding. When called from index_repository, a BatchedEmbedder
                is passed here to combine texts across files.
        """
        logger.info(f"[index_file] Enter: {file_path} repo_id={repo_id}")

        indexer = content_indexer or self.content_indexer

        prepared = prepared_override
        indexed = indexed_override
        repo_path: str | None = None

        # If we already have indexed content, we only need repo metadata for
        # graph/vector persistence. Resolve it without starting a session here.
        if indexed_override is not None:
            async with self.session_factory() as session:
                repo = await session.get(Repository, repo_id)
                if not repo:
                    logger.error(f"Repository {repo_id} not found")
                    return
                repo_path = await self._resolve_project_path(repo)
            if repo_path is None:
                logger.warning(
                    f"[index_file] No resolvable project path for repo {repo_id}. Skipping {file_path}."
                )
                return

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

                # 1. Prepare (skip if provided by caller)
                if prepared is None:
                    prepared = await self.file_preparer.prepare(
                        file_path, repo, session, force=force, repo_path=repo_path
                    )
                    if not prepared:
                        return

                # 2. Index Content (skip if provided by caller)
                if indexed is None:
                    indexed = await indexer.index(
                        file_path, prepared.content, prepared.rel_path
                    )
                    if not indexed:
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

                    await asyncio.to_thread(
                        vector_store.upsert_code_chunks,
                        chunks_for_vec,
                        indexed.embeddings,
                    )
                else:
                    logger.debug(f"Skipping vector upsert for {prepared.rel_path}: embeddings disabled or not generated.")

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
                    logger.debug("[IndexingService] Graph sync skipped (not supported in embedded mode)")

            except Exception as e:
                logger.error(f"Error indexing file {file_path}: {e}")
                await session.rollback()

    async def _prepare_and_extract(
        self,
        file_path: str,
        repo_id: int,
        force: bool,
        content_indexer: ContentIndexer,
    ) -> tuple[PreparedFile, IndexedContent] | None:
        """Prepare and extract a single file without embedding."""
        async with self.session_factory() as session:
            try:
                repo = await session.get(Repository, repo_id)
                if not repo:
                    logger.error(f"Repository {repo_id} not found")
                    return None

                repo_path = await self._resolve_project_path(repo)
                if not repo_path:
                    return None

                prepared = await self.file_preparer.prepare(
                    file_path, repo, session, force=force, repo_path=repo_path
                )
                if not prepared:
                    return None

                extracted = await content_indexer.extract(
                    file_path, prepared.content, prepared.rel_path
                )
                if extracted is None:
                    return None

                all_docs, entities, relations, file_summary_doc = extracted
                indexed = IndexedContent(
                    documents=all_docs,
                    entities=entities,
                    relations=relations,
                    embeddings=[],
                    file_summary_doc=file_summary_doc,
                )
                return prepared, indexed
            except Exception as e:
                logger.error(f"Error preparing/extracting {file_path}: {e}")
                await session.rollback()
                return None

    async def _embed_all(
        self,
        items: list[tuple[PreparedFile, IndexedContent]],
        batched_embedder: BatchedEmbedder,
    ) -> None:
        """Embed all collected texts and attach embeddings to each IndexedContent.

        The texts are processed in chunks capped by the underlying embedder's
        batch size. This prevents a single huge ``model.encode()`` call from
        monopolizing the CPU for minutes and keeps the worker responsive.
        """
        if not items or not batched_embedder:
            return

        # Build a flat list of texts with pointers back to (item_index, doc_index).
        texts: list[str] = []
        text_map: list[tuple[int, int]] = []
        for item_idx, (_, indexed) in enumerate(items):
            for doc_idx, doc in enumerate(indexed.documents):
                skel = doc.metadata.get("skeleton")
                if skel:
                    text = skel
                else:
                    text = doc.content[:8000]
                texts.append(text)
                text_map.append((item_idx, doc_idx))

        if not texts:
            return

        logger.info(f"[_embed_all] Embedding {len(texts)} texts across {len(items)} files")

        # Determine a safe chunk size.  The BatchedEmbedder already caps batches,
        # but splitting here keeps memory bounded and yields regular progress.
        chunk_size = max(batched_embedder._max_batch_size, 1)
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), chunk_size):
            chunk = texts[i : i + chunk_size]
            logger.info(f"[_embed_all] Embedding chunk {i // chunk_size + 1}/{(len(texts) - 1) // chunk_size + 1} ({len(chunk)} texts)")
            chunk_embeddings = await batched_embedder.embed_documents(chunk)
            if len(chunk_embeddings) != len(chunk):
                raise RuntimeError(
                    f"Expected {len(chunk)} embeddings, got {len(chunk_embeddings)}"
                )
            all_embeddings.extend(chunk_embeddings)

        for (item_idx, _doc_idx), embedding in zip(text_map, all_embeddings, strict=False):
            items[item_idx][1].embeddings.append(embedding)

    async def _persist_indexed(
        self,
        file_path: str,
        repo_id: int,
        prepared: PreparedFile,
        indexed: IndexedContent,
    ) -> bool:
        """Persist a pre-prepared, pre-embedded file to SQL, vector and graph stores."""
        try:
            await self.index_file(
                file_path,
                repo_id,
                prepared_override=prepared,
                indexed_override=indexed,
            )
            return True
        except Exception as e:
            logger.error(f"Error persisting {file_path}: {e}")
            return False

    async def remove_file(self, file_path: str, repo_id: int):
        """Remove a file from SQL and graph indexes."""
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

        logger.info(f"Starting full indexing for repo {repo_id} at {repo_path} (Force={force})")

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

        total_files = len(filtered_files)

        # Use a three-phase pipeline, but embed and persist in small windows so
        # that progress survives worker restarts/crashes. A single huge embed
        # call can take hours on CPU; if it is interrupted before any files are
        # persisted, the next restart has to redo everything. We therefore:
        #   1. Extract all files cheaply in parallel.
        #   2. Walk through the extracted files in windows of ~16 texts,
        #      embed each window, then immediately persist those files.
        EXTRACT_CONCURRENCY = 4
        PERSIST_CONCURRENCY = 2
        extract_semaphore = asyncio.Semaphore(EXTRACT_CONCURRENCY)
        persist_semaphore = asyncio.Semaphore(PERSIST_CONCURRENCY)

        # Window size matches the LocalEmbedder encode batch cap so that each
        # window results in roughly one model.encode() call. This preserves the
        # cross-file batching benefit while keeping persistence granular.
        TEXTS_PER_WINDOW = 16

        batched_embedder = BatchedEmbedder(
            self.embedder, max_batch_size=TEXTS_PER_WINDOW, max_wait_ms=50
        )
        batched_content_indexer = ContentIndexer(self.extractor, batched_embedder)

        async def _extract_one(file_path: str) -> tuple[PreparedFile, IndexedContent] | None:
            async with extract_semaphore:
                return await self._prepare_and_extract(
                    file_path, repo_id, force, batched_content_indexer
                )

        # Phase 1: prepare + extract all files concurrently.
        logger.info(f"Phase 1/3: extracting up to {total_files} files")
        extract_tasks = [asyncio.create_task(_extract_one(f)) for f in filtered_files]
        extract_results = await asyncio.gather(*extract_tasks, return_exceptions=True)

        prepared_items: list[tuple[PreparedFile, IndexedContent]] = []
        extract_error_count = 0
        for file_path, result in zip(filtered_files, extract_results, strict=False):
            if isinstance(result, Exception):
                extract_error_count += 1
                logger.error(f"Failed to extract {file_path}: {result}")
            elif result is not None:
                prepared_items.append(result)

        logger.info(
            f"Phase 1 complete: {len(prepared_items)} files extracted, "
            f"{extract_error_count} errors"
        )

        # Phase 2+3: embed and persist in windows.
        logger.info("Phase 2/3: embedding and persisting in windows")
        indexed_count = 0
        persist_error_count = 0
        window: list[tuple[PreparedFile, IndexedContent, int]] = []
        window_texts: list[str] = []

        async def _persist_one(item: tuple[PreparedFile, IndexedContent]) -> bool:
            async with persist_semaphore:
                prepared, indexed = item
                return await self._persist_indexed(
                    prepared.file_path, repo_id, prepared, indexed
                )

        async def _flush_window() -> None:
            nonlocal indexed_count, persist_error_count
            if not window:
                return

            if self.embedder is None:
                # Embeddings disabled: persist the window immediately with empty
                # embeddings. This keeps the SQL/graph index up-to-date while
                # avoiding the CPU-heavy local embedding step.
                window_items: list[tuple[PreparedFile, IndexedContent]] = []
                for prepared, indexed, _text_count in window:
                    indexed.embeddings = []
                    window_items.append((prepared, indexed))
                window.clear()
                window_texts.clear()

                persist_tasks = [
                    asyncio.create_task(_persist_one(item)) for item in window_items
                ]
                persist_results = await asyncio.gather(*persist_tasks, return_exceptions=True)
                for result in persist_results:
                    if isinstance(result, Exception):
                        persist_error_count += 1
                        logger.error(f"Window persist failed: {result}")
                    elif result:
                        indexed_count += 1
                    else:
                        persist_error_count += 1

                logger.info(
                    f"Progress: {indexed_count}/{len(prepared_items)} files "
                    f"({persist_error_count} errors)"
                )
                return

            logger.info(
                f"[_embed_window] Embedding window of {len(window)} files, "
                f"{len(window_texts)} texts"
            )
            try:
                embeddings = await batched_embedder.embed_documents(window_texts)
            except Exception as e:
                logger.error(f"Window embedding failed: {e}")
                for _, _, _ in window:
                    persist_error_count += 1
                window.clear()
                window_texts.clear()
                return

            # Distribute embeddings back to each IndexedContent.
            offset = 0
            window_items = []
            for prepared, indexed, text_count in window:
                indexed.embeddings = embeddings[offset : offset + text_count]
                offset += text_count
                window_items.append((prepared, indexed))

            window.clear()
            window_texts.clear()

            # Persist the window's files concurrently (bounded by DB).
            persist_tasks = [
                asyncio.create_task(_persist_one(item)) for item in window_items
            ]
            persist_results = await asyncio.gather(*persist_tasks, return_exceptions=True)

            for result in persist_results:
                if isinstance(result, Exception):
                    persist_error_count += 1
                    logger.error(f"Window persist failed: {result}")
                elif result:
                    indexed_count += 1
                else:
                    persist_error_count += 1

            logger.info(
                f"Progress: {indexed_count}/{len(prepared_items)} files "
                f"({persist_error_count} errors)"
            )

        for prepared, indexed in prepared_items:
            texts = []
            for doc in indexed.documents:
                skel = doc.metadata.get("skeleton")
                texts.append(skel if skel else doc.content[:8000])

            window.append((prepared, indexed, len(texts)))
            window_texts.extend(texts)

            if len(window_texts) >= TEXTS_PER_WINDOW:
                await _flush_window()

        # Flush any remaining files in the final window.
        await _flush_window()
        await batched_embedder.close()

        error_count = extract_error_count + persist_error_count
        logger.info(f"Full indexing complete. Indexed: {indexed_count}, Errors: {error_count}")
