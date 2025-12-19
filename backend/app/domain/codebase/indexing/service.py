import os
import glob
from typing import List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.logging import logger
from app.domain.codebase.indexing.base import BaseExtractor, BaseEmbedder
from app.domain.codebase.indexing.extractors.treesitter_extractor import TreeSitterExtractor
from app.domain.codebase.indexing.vectors.openai_embedder import OpenAIEmbedder
from app.infrastructure.database.sql.models import Repository, SourceFile, CodeChunk
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.domain.project.service import project_context_manager


class IndexingService:
    def __init__(self, session: AsyncSession = None):
        self.session_factory = AsyncSessionLocal
        self.extractor: BaseExtractor = TreeSitterExtractor()
        self.embedder: BaseEmbedder = OpenAIEmbedder()

    async def get_or_create_repo(self, path: str, name: str) -> Repository:
        async with self.session_factory() as session:
            # Check existing
            stmt = select(Repository).where(Repository.local_path == path)
            result = await session.execute(stmt)
            repo = result.scalars().first()

            if repo:
                return repo

            if repo:
                return repo

            # Resolve Project ID dynamically
            project_id = 1
            try:
                projects = await project_context_manager.scan_projects()
                abs_path = os.path.abspath(path)
                for p in projects:
                    if p.get("path") and os.path.abspath(p.get("path")) == abs_path:
                        project_id = p.get("id", 1)
                        break
            except Exception as e:
                logger.warning(f"Failed to resolve project_id for {path}, using default 1: {e}")

            # Create Repo
            repo = Repository(project_id=project_id, name=name, url="local", local_path=path)
            session.add(repo)
            await session.commit()
            await session.refresh(repo)
            return repo

    async def index_file(self, file_path: str, repo_id: int):
        """
        Index a single file. (Incremental update)
        """
        async with self.session_factory() as session:
            try:
                repo = await session.get(Repository, repo_id)
                if not repo:
                    logger.error(f"Repository {repo_id} not found")
                    return

                rel_path = os.path.relpath(file_path, repo.local_path)

                # Check extension
                valid_extensions = (".py", ".js", ".ts", ".go", ".java", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".rs", ".php", ".rb", ".md")
                if not file_path.endswith(valid_extensions):
                    return

                # Read content
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")
                    return

                # Checksum Verification
                import hashlib
                new_checksum = hashlib.md5(content.encode("utf-8")).hexdigest()

                # 1. Get or Create SourceFile (to check previous checksum)
                stmt = select(SourceFile).where(SourceFile.repository_id == repo_id, SourceFile.path == rel_path)
                result = await session.execute(stmt)
                source_file = result.scalars().first()

                if source_file and source_file.checksum == new_checksum:
                    # logger.debug(f"Skipping {rel_path} (Unchanged)")
                    return

                # If we are here, it's new or modified
                logger.info(f"Indexing {rel_path} (Checksum mismatch or new)")

                # Extract
                docs = await self.extractor.extract(file_path, content)
                if not docs:
                    return  # No chunks extracted due to empty or parse error

                if not source_file:
                    source_file = SourceFile(
                        repository_id=repo_id,
                        path=rel_path,
                        checksum=new_checksum
                    )
                    session.add(source_file)
                    await session.flush()
                else:
                    # Update Checksum
                    source_file.checksum = new_checksum
                    source_file.updated_at = datetime.utcnow()  # Trigger update via ORM or manual
                    session.add(source_file)

                # 2. Clear old chunks (Full Refresh for this file)
                await session.execute(delete(CodeChunk).where(CodeChunk.file_id == source_file.id))

                # 3. Embed & Insert
                texts = [d.content for d in docs]
                # Embed (Mock or Real based on Embedder implementation)
                embeddings = await self.embedder.embed_documents(texts)

                for doc, vector in zip(docs, embeddings):
                    chunk = CodeChunk(
                        file_id=source_file.id,
                        chunk_type=doc.metadata.get("type", "unknown"),
                        identifier=doc.metadata.get("name", "unknown"),
                        start_line=doc.metadata.get("start_line", 0),
                        end_line=doc.metadata.get("end_line", 0),
                        content=doc.content,
                        embedding=vector
                    )
                    session.add(chunk)

                await session.commit()
                # logger.debug(f"Indexed {rel_path}")

            except Exception as e:
                logger.error(f"Error indexing file {file_path}: {e}")
                await session.rollback()

    async def index_repository(self, repo_path: str, repo_id: int):
        """
        Main entry point to index a repository on disk.
        """
        logger.info(f"Starting full indexing for repo {repo_id} at {repo_path}")

        files = glob.glob(os.path.join(repo_path, "**", "*"), recursive=True)

        valid_exts = (".py", ".js", ".ts", ".go", ".java", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".rs", ".php", ".rb", ".md")

        filtered_files = []
        for f in files:
            if not os.path.isfile(f): continue
            if not f.endswith(valid_exts): continue

            # Exclude directories
            if any(part in f.split(os.sep) for part in [".venv", "venv", "node_modules", ".git", "__pycache__"]):
                continue

            filtered_files.append(f)

        # Sequentially index files (could be parallelized)
        for f in filtered_files:
            await self.index_file(f, repo_id)

        logger.info("Full indexing complete.")
