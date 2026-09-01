import asyncio
import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.evocloud import evocloud_manager
from app.core.file import get_file_ext
from app.core.project.utils import get_project_path
from app.domain.codebase.constants import (
    BATCH_MAX_WAIT_MS,
    EMBEDDING_TEXT_CAP,
    EXTRACT_CONCURRENCY,
    REPO_SYNC_STATUS_PENDING_CREATION,
    REPO_SYNC_STATUS_SYNCED,
    TEXTS_PER_WINDOW,
)
from app.domain.codebase.indexing.components.content_indexer import ContentIndexer
from app.domain.codebase.indexing.components.file_preparer import FilePreparer
from app.domain.codebase.indexing.components.sql_persister import SQLPersister
from app.domain.codebase.indexing.extractors.treesitter_extractor import (
    TreeSitterExtractor,
)
from app.domain.codebase.schemas import IndexedContent, PreparedFile
from app.infrastructure.database import session_scope
from app.infrastructure.database.vector import get_vector_store
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
            sync_status = REPO_SYNC_STATUS_SYNCED

            if not resolved_pid:
                try:
                    projects = await evocloud_manager.scan_projects()
                    abs_path = os.path.abspath(path)
                    for p in projects:
                        if p.get("path") and os.path.abspath(p.get("path")) == abs_path:
                            resolved_pid = p.get("id")
                            break
                except Exception as e:
                    logger.warning(
                        f"Failed to resolve project_id for {path}: {e}", exc_info=True
                    )

            if not resolved_pid:
                sync_status = REPO_SYNC_STATUS_PENDING_CREATION

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
        if repo.local_path and os.path.isdir(repo.local_path):
            return repo.local_path
        if repo.project_id is not None:
            resolved = await get_project_path(repo.project_id)
            if resolved and os.path.isdir(resolved):
                return resolved
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
        skip_vector_upsert: bool = False,
        _vector_collector: list | None = None,
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
            skip_vector_upsert: If True, skip vector store upsert and instead
                append vector data to _vector_collector for batch processing.
            _vector_collector: Optional list to collect vector data for batched
                upsert. Requires skip_vector_upsert=True.
        """
        logger.info(f"[index_file] Enter: {file_path} repo_id={repo_id}")

        indexer = content_indexer or self.content_indexer

        prepared = prepared_override
        indexed = indexed_override

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

                if prepared is None:
                    prepared = await self.file_preparer.prepare(
                        file_path, repo, session, force=force, repo_path=repo_path
                    )
                    if not prepared:
                        return

                if indexed is None:
                    indexed = await indexer.index(
                        file_path, prepared.content, prepared.rel_path
                    )
                    if not indexed:
                        return

                source_file = await self.file_preparer.create_or_update_source_file(
                    prepared, session
                )
                await self.sql_persister.clear_old_data(source_file, session)
                await self.sql_persister.persist(indexed, source_file, session)

                if indexed.embeddings:
                    if skip_vector_upsert and _vector_collector is not None:
                        chunks_for_vec = []
                        for doc in indexed.documents:
                            chunks_for_vec.append({
                                "content": doc.content,
                                "file_path": prepared.rel_path,
                                "repository_id": str(repo_id),
                                "chunk_type": doc.metadata.get("type", "unknown"),
                                "identifier": doc.metadata.get("name", "unknown"),
                                "start_line": doc.metadata.get("start_line", 0),
                                "end_line": doc.metadata.get("end_line", 0),
                                "language": get_file_ext(prepared.file_path),
                            })
                        _vector_collector.append((chunks_for_vec, indexed.embeddings))
                    else:
                        vector_store = get_vector_store(project_path=repo_path)
                        chunks_for_vec = []
                        for doc in indexed.documents:
                            chunks_for_vec.append({
                                "content": doc.content,
                                "file_path": prepared.rel_path,
                                "repository_id": str(repo_id),
                                "chunk_type": doc.metadata.get("type", "unknown"),
                                "identifier": doc.metadata.get("name", "unknown"),
                                "start_line": doc.metadata.get("start_line", 0),
                                "end_line": doc.metadata.get("end_line", 0),
                                "language": get_file_ext(prepared.file_path),
                            })
                        await asyncio.to_thread(
                            vector_store.upsert_code_chunks,
                            chunks_for_vec,
                            indexed.embeddings,
                        )
                else:
                    logger.debug(f"Skipping vector upsert for {prepared.rel_path}: embeddings disabled or not generated.")

            except Exception as e:
                logger.exception(f"Error indexing file {file_path}: {e}")
                if prepared is not None:
                    try:
                        await self.file_preparer.mark_source_file_failed(prepared.source_file, session)
                        await session.commit()
                    except Exception as mark_err:
                        logger.exception(f"Failed to mark source_file as failed: {mark_err}")
                        await session.rollback()
                else:
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

                extracted = await content_indexer.extract(file_path, prepared.content, prepared.rel_path)
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
                logger.exception(f"Error preparing/extracting {file_path}: {e}")
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
                    text = doc.content[:EMBEDDING_TEXT_CAP]
                texts.append(text)
                text_map.append((item_idx, doc_idx))

        if not texts:
            return

        logger.info(f"Embedding {len(texts)} texts across {len(items)} files")

        # Determine a safe chunk size.  The BatchedEmbedder already caps batches,
        # but splitting here keeps memory bounded and yields regular progress.
        chunk_size = max(batched_embedder._max_batch_size, 1)
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), chunk_size):
            chunk = texts[i : i + chunk_size]
            logger.info(f"Embedding chunk {i // chunk_size + 1}/{(len(texts) - 1) // chunk_size + 1} ({len(chunk)} texts)")
            chunk_embeddings = await batched_embedder.embed_documents(chunk)
            if len(chunk_embeddings) != len(chunk):
                raise RuntimeError(f"Expected {len(chunk)} embeddings, got {len(chunk_embeddings)}")
            all_embeddings.extend(chunk_embeddings)

        for (item_idx, _doc_idx), embedding in zip(text_map, all_embeddings, strict=False):
            items[item_idx][1].embeddings.append(embedding)

    async def remove_file(self, file_path: str, repo_id: int):
        """Remove a file from SQL indexes."""
        async with self.session_factory() as session:
            try:
                repo = await session.get(Repository, repo_id)
                if not repo:
                    return

                repo_path = await self._resolve_project_path(repo)
                if not repo_path:
                    logger.warning(f"[remove_file] No resolvable project path for repo {repo_id}. Skipping {file_path}.")
                    return

                rel_path = os.path.relpath(file_path, repo_path)

                stmt = select(SourceFile).where(
                    SourceFile.repository_id == repo_id, SourceFile.path == rel_path
                )
                result = await session.execute(stmt)
                source_file = result.scalars().first()

                if source_file:
                    await self.sql_persister.clear_old_data(source_file, session)
                    await session.delete(source_file)
                    logger.info(f"Removed {rel_path} from SQL Index")

            except Exception as e:
                logger.exception(f"Error removing file {file_path}: {e}")
                await session.rollback()

    async def move_file(self, src_path: str, dest_path: str, repo_id: int):
        """Handle file move/rename via remove + re-index."""
        # 1. Remove Old
        await self.remove_file(src_path, repo_id)

        # 2. Index New
        # Ensure new path exists logic is handled by caller or index_file just reads it.
        # If this is triggered by Watcher, file already exists at dest_path.
        if os.path.exists(dest_path):
            await self.index_file(dest_path, repo_id)
            logger.info(f"Moved (Re-indexed) {src_path} -> {dest_path}")

    async def index_repository(self, repo_path: str, repo_id: int, force: bool = False):
        """
        Main entry point to index a repository on disk.
        """
        if not repo_path or not os.path.isdir(repo_path):
            logger.warning(f"[index_repository] Skipping repo {repo_id}: invalid path {repo_path}")
            return

        logger.info(f"Starting full indexing for repo {repo_id} at {repo_path} (Force={force})")

        from app.constants import BLACKLIST_DIRS
        from app.core.file.service import walk_tree

        # Walk directory (offloaded to thread to avoid blocking the event loop)
        # FileTraverser now handles .gitignore filtering internally via gitignore_root.
        filtered_files = await asyncio.to_thread(
            lambda: list(
                walk_tree(
                    repo_path,
                    filter_func=self.file_preparer.should_index,
                    exclude_dirs=BLACKLIST_DIRS,
                    gitignore_root=repo_path,
                )
            )
        )

        logger.info(f"Found {len(filtered_files)} valid files to index (Applied .gitignore).")

        total_files = len(filtered_files)

        # Use a three-phase pipeline, but embed and persist in small windows so
        # that progress survives worker restarts/crashes. A single huge embed
        # call can take hours on CPU; if it is interrupted before any files are
        # persisted, the next restart has to redo everything. We therefore:
        #   1. Extract all files cheaply in parallel.
        #   2. Walk through the extracted files in windows of ~TEXTS_PER_WINDOW
        #      texts, embed each window, then immediately persist those files.
        extract_semaphore = asyncio.Semaphore(EXTRACT_CONCURRENCY)

        # Window size matches the BCE model's optimal encode batch size.
        # Larger batches give significantly better throughput (336 vs 112 texts/s).
        # Each window results in roughly one model.encode() call.

        batched_embedder = BatchedEmbedder(
            self.embedder,
            max_batch_size=TEXTS_PER_WINDOW,
            max_wait_ms=BATCH_MAX_WAIT_MS,
        )
        batched_content_indexer = ContentIndexer(self.extractor, batched_embedder)

        async def _extract_one(file_path: str) -> tuple[PreparedFile, IndexedContent] | None:
            async with extract_semaphore:
                return await self._prepare_and_extract(file_path, repo_id, force, batched_content_indexer)

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
        all_window_vectors: list = []
        last_repo_path: str | None = None
        window: list[tuple[PreparedFile, IndexedContent, int]] = []
        window_texts: list[str] = []

        async def _flush_window() -> None:
            nonlocal \
                indexed_count, \
                persist_error_count, \
                all_window_vectors, \
                last_repo_path
            if not window:
                return

            window_items: list[tuple[PreparedFile, IndexedContent]] = []
            vector_collector: list = []

            if self.embedder is None:
                for prepared, indexed, _ in window:
                    indexed.embeddings = []
                    window_items.append((prepared, indexed))
                window.clear()
                window_texts.clear()
            else:
                logger.info(
                    f"[_embed_window] Embedding window of {len(window)} files, "
                    f"{len(window_texts)} texts"
                )
                try:
                    embeddings = await batched_embedder.embed_documents(window_texts)
                except Exception as e:
                    logger.warning(
                        f"[_embed_window] Window embedding failed: {e}. "
                        "Falling back to persisting files without embeddings.",
                        exc_info=True,
                    )
                    embeddings = [[] for _ in window_texts]

                offset = 0
                for prepared, indexed, text_count in window:
                    indexed.embeddings = embeddings[offset : offset + text_count]
                    offset += text_count
                    window_items.append((prepared, indexed))
                window.clear()
                window_texts.clear()

            # Batch-persist all files in a single DB session,
            # then batch upsert vectors across the window.
            try:
                async with self.session_factory() as session:
                    repo = await session.get(Repository, repo_id)
                    if not repo:
                        logger.error(
                            f"Repository {repo_id} not found during window persist"
                        )
                        return
                    repo_path = await self._resolve_project_path(repo)
                    if not repo_path:
                        logger.warning(
                            f"No resolvable project path for repo {repo_id}. "
                            f"Skipping {len(window_items)} files."
                        )
                        return

                    # Create/update all source files, then batch-clear + batch-persist.
                    source_files: list[SourceFile] = []
                    for prepared, _indexed in window_items:
                        sf = await self.file_preparer.create_or_update_source_file(
                            prepared, session
                        )
                        source_files.append(sf)

                    await self.sql_persister.batch_clear(source_files, session)
                    await self.sql_persister.batch_persist(
                        [
                            (indexed, sf)
                            for (_, indexed), sf in zip(window_items, source_files)
                        ],
                        session,
                    )

                    for prepared, indexed in window_items:
                        if indexed.embeddings:
                            chunks_for_vec = [
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
                                for doc in indexed.documents
                            ]
                            vector_collector.append((chunks_for_vec, indexed.embeddings))

                    window_ok = True

                if window_ok:
                    indexed_count += len(window_items)
                    last_repo_path = repo_path
                    all_window_vectors.extend(vector_collector)

            except Exception as e:
                logger.exception(f"Window persist failed: {e}")
                window_ok = False

            if not window_ok:
                persist_error_count += len(window_items)

            logger.info(
                f"Progress: {indexed_count}/{len(prepared_items)} files "
                f"({persist_error_count} errors)"
            )

        for prepared, indexed in prepared_items:
            texts = []
            for doc in indexed.documents:
                skel = doc.metadata.get("skeleton")
                texts.append(skel if skel else doc.content[:EMBEDDING_TEXT_CAP])

            window.append((prepared, indexed, len(texts)))
            window_texts.extend(texts)

            if len(window_texts) >= TEXTS_PER_WINDOW:
                await _flush_window()

        # Flush any remaining files in the final window.
        await _flush_window()
        await batched_embedder.close()

        # Single batch vector upsert for all files in the repository.
        if all_window_vectors and last_repo_path:
            try:
                vector_store = get_vector_store(project_path=last_repo_path)
                all_chunks: list = []
                all_embeddings: list[list[float]] = []
                for chunks_vec, embs in all_window_vectors:
                    all_chunks.extend(chunks_vec)
                    all_embeddings.extend(embs)
                await asyncio.to_thread(
                    vector_store.upsert_code_chunks,
                    all_chunks,
                    all_embeddings,
                )
                logger.info(f"Vector upsert complete: {len(all_chunks)} chunks")
            except Exception as e:
                logger.exception(f"Final vector upsert failed: {e}")

        error_count = extract_error_count + persist_error_count
        logger.info(f"Full indexing complete. Indexed: {indexed_count}, Errors: {error_count}")
