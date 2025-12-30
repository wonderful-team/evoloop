import glob
import os
from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.codebase.indexing.base import BaseEmbedder
from app.domain.codebase.indexing.extractors.treesitter_extractor import TreeSitterExtractor
from app.domain.codebase.indexing.vectors.openai_embedder import OpenAIEmbedder
from app.domain.project.service import project_context_manager
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.infrastructure.database.sql.models import Repository, SourceFile, CodeChunk, CodeEntity, CodeRelation
from app.logging import logger


class IndexingService:
    def __init__(self, session: AsyncSession = None):
        self.session_factory = AsyncSessionLocal
        # Note: Extractor now returns ExtractionResult
        self.extractor = TreeSitterExtractor()
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
        # FileFilter check
        from app.domain.codebase.filter import FileFilter
        file_filter = FileFilter()
        if not file_filter.should_include(file_path):
            return

        async with self.session_factory() as session:
            try:
                repo = await session.get(Repository, repo_id)
                if not repo:
                    logger.error(f"Repository {repo_id} not found")
                    return
                # ... rest of the function logic ...
                # Wait, I should better not indent everything inside session if not needed, 
                # or just copy-paste the existing logic but keep the check outside.
                
                rel_path = os.path.relpath(file_path, repo.local_path)

                # Check extension - FileFilter handled generic text check, but specific languages?
                valid_extensions = (".py", ".js", ".ts", ".go", ".java", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".rs", ".php", ".rb", ".md")
                if not file_path.endswith(valid_extensions):
                    # FileFilter might pass a .txt or .json, but indexing service might strictly want code.
                    # Let's keep this check for now to be safe, or expand it using constants.
                    # Or rely on Extractor capability. TreeSitterExtractor supports specific languages.
                    # Let's keep it to avoid regression but rely on FileFilter for "Bad Files"
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
                extraction_result = await self.extractor.extract(file_path, content)
                
                # Unpack result
                # Support both old list return (if any other extractor used) and new object
                if isinstance(extraction_result, list):
                     docs = extraction_result
                     entities = []
                     relations = []
                else:
                     docs = extraction_result.documents
                     entities = extraction_result.entities
                     relations = extraction_result.relations

                if not docs and not entities:
                    # Safe Indexing Check:
                    # If file content is substantial (>50 chars?) but we got NOTHING,
                    # it might be a parse error (dirty code).
                    # We skip wiping the DB to preserve "Last Known Good".
                    if len(content.strip()) > 50:
                        logger.warning(f"Safe Indexing: Skipping {rel_path} - non-empty content but no extracted data.")
                        return
                    
                    # If content is small (empty file), we proceed to clear DB.
                    # Fallthrough to update SourceFile but clear chunks.
                    pass

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
                    source_file.updated_at = datetime.utcnow()
                    session.add(source_file)

                # 2. Clear old chunks, entities and relations (Full Refresh for this file)
                await session.execute(delete(CodeChunk).where(CodeChunk.file_id == source_file.id))
                
                # Delete relations first (using subquery on entities before they are gone)
                subq = select(CodeEntity.id).where(CodeEntity.file_id == source_file.id)
                await session.execute(delete(CodeRelation).where(CodeRelation.source_entity_id.in_(subq)))
                
                # Then delete entities
                await session.execute(delete(CodeEntity).where(CodeEntity.file_id == source_file.id))

                # 3. Embed & Insert Chunks
                if docs:
                    texts = [d.content for d in docs]
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
                
                # 4. Insert Entities and Build Map
                name_to_id = {}
                for ent in entities:
                    entity_record = CodeEntity(
                        file_id=source_file.id,
                        name=ent.name,
                        type=ent.type,
                        full_name=ent.full_name,
                        start_line=ent.start_line,
                        end_line=ent.end_line
                    )
                    session.add(entity_record)
                    await session.flush() # Flush to get ID
                    name_to_id[ent.full_name] = entity_record.id

                # 5. Insert Relations
                for rel in relations:
                    source_id = name_to_id.get(rel.source_full_name)
                    if not source_id:
                        continue # Cannot link if source is missing (should not happen if logic is correct)
                    
                    # Try to resolve target locally (generic logic, incomplete for full project graph pass)
                    # For now we mostly rely on target_name for cross-file links
                    target_id = name_to_id.get(rel.target_full_name)
                    
                    rel_record = CodeRelation(
                        source_entity_id=source_id,
                        target_entity_id=target_id, # Can be None
                        target_name=rel.target_full_name,
                        relation_type=rel.relation_type
                    )
                    session.add(rel_record)

                await session.commit()
                
                # 6. Sync to Neo4j
                try:
                    from app.infrastructure.database.graph.driver import get_graph_db
                    driver = await get_graph_db()
                    async with driver.session() as n4j:
                        # Ensure we use project_id context
                        await n4j.run("""
                            MERGE (f:File {path: $path, project_id: $pid}) 
                            SET f.last_indexed = timestamp(), f.pg_id = $pg_id
                        """, path=rel_path, pid=repo.project_id, pg_id=source_file.id)
                except Exception as e:
                    logger.warning(f"Neo4j Sync Failed for {rel_path}: {e}")

                # logger.debug(f"Indexed {rel_path}")

            except Exception as e:
                logger.error(f"Error indexing file {file_path}: {e}")
                await session.rollback()

    async def remove_file(self, file_path: str, repo_id: int):
        """
        Handle file deletion.
        """
        async with self.session_factory() as session:
            repo = await session.get(Repository, repo_id)
            if not repo: return
            
            rel_path = os.path.relpath(file_path, repo.local_path)
            
            # 1. Postgres Delete
            stmt = select(SourceFile).where(SourceFile.repository_id == repo_id, SourceFile.path == rel_path)
            result = await session.execute(stmt)
            source_file = result.scalars().first()
            
            if source_file:
                # CodeChunk/Entity cascades usually configured in DB? 
                # If not, manual delete required. Models usually have cascade='all, delete'.
                # Assuming cascade works or manual delete needed. 
                # Let's do manual delete to be safe as previously done in index_file
                await session.execute(delete(CodeChunk).where(CodeChunk.file_id == source_file.id))
                subq = select(CodeEntity.id).where(CodeEntity.file_id == source_file.id)
                await session.execute(delete(CodeRelation).where(CodeRelation.source_entity_id.in_(subq)))
                await session.execute(delete(CodeEntity).where(CodeEntity.file_id == source_file.id))
                
                await session.delete(source_file)
                await session.commit()
                logger.info(f"Removed {rel_path} from Index")

            # 2. Neo4j Delete
            try:
                from app.infrastructure.database.graph.driver import get_graph_db
                driver = await get_graph_db()
                async with driver.session() as n4j:
                    await n4j.run("""
                        MATCH (f:File {path: $path, project_id: $pid})
                        DETACH DELETE f
                    """, path=rel_path, pid=repo.project_id)
            except Exception as e:
                logger.warning(f"Neo4j Delete Failed for {rel_path}: {e}")

    async def move_file(self, src_path: str, dest_path: str, repo_id: int):
        """
        Handle file move/rename.
        """
        async with self.session_factory() as session:
            repo = await session.get(Repository, repo_id)
            if not repo: return
            
            old_rel = os.path.relpath(src_path, repo.local_path)
            new_rel = os.path.relpath(dest_path, repo.local_path)
            
            # 1. Postgres Update
            stmt = select(SourceFile).where(SourceFile.repository_id == repo_id, SourceFile.path == old_rel)
            result = await session.execute(stmt)
            source_file = result.scalars().first()
            
            if source_file:
                source_file.path = new_rel
                source_file.updated_at = datetime.utcnow()
                session.add(source_file)
                await session.commit()
                logger.info(f"Moved {old_rel} -> {new_rel} in Index")
                
                # Trigger re-indexing of content?
                # If content didn't change (just move), re-indexing chunks might be needed if they store metadata?
                # Chunks usually store content. If generic, it's fine.
                # But we might want to re-verify content.
                # For now, just link update is sufficient for "Stable ID".
            
            # 2. Neo4j Update (CRITICAL)
            try:
                from app.infrastructure.database.graph.driver import get_graph_db
                driver = await get_graph_db()
                async with driver.session() as n4j:
                    await n4j.run("""
                        MATCH (f:File {path: $old_path, project_id: $pid})
                        SET f.path = $new_path
                    """, old_path=old_rel, new_path=new_rel, pid=repo.project_id)
            except Exception as e:
                logger.warning(f"Neo4j Move Failed: {e}")

    async def index_repository(self, repo_path: str, repo_id: int):
        """
        Main entry point to index a repository on disk.
        """
        logger.info(f"Starting full indexing for repo {repo_id} at {repo_path}")
        
        from app.domain.codebase.filter import FileFilter
        file_filter = FileFilter()

        # Build inclusions/exclusions from config if needed.
        # For now, we rely on FileFilter defaults which include basic blacklists.
        # Ideally we should read .gitignore here, but FileFilter doesn't do that yet automatically?
        # FileFilter.should_include handles standard exclusions + compression checks.
        
        # Walk directory manually to avoid loading EVERYTHING into memory if repo is huge?
        # But `glob` or `os.walk` are generators. `glob` returns a list.
        # Let's use os.walk for better control and efficiency.
        
        filtered_files = []
        for root, dirs, files in os.walk(repo_path):
            # 1. Directory Filtering (Prune traversal)
            # We must modify 'dirs' in-place to prune logic.
            # But FileFilter.should_include works on file paths.
            # We can use constants.BLACKLIST_DIRS
            from app.domain.codebase.constants import BLACKLIST_DIRS
            d_to_remove = []
            for d in dirs:
                if d in BLACKLIST_DIRS or d.startswith('.'):
                     d_to_remove.append(d)
            for d in d_to_remove:
                dirs.remove(d)

            for f in files:
                full_path = os.path.join(root, f)
                
                # Use the robust FileFilter
                if file_filter.should_include(full_path):
                    # Additional check for supported language extensions
                    # (Unless FileFilter is configured with inclusions)
                    # For now, we keep the strict extension check for the indexer
                    # because the *Extractor* only supports these.
                    valid_exts = (".py", ".js", ".ts", ".go", ".java", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".rs", ".php", ".rb", ".md")
                    if full_path.endswith(valid_exts):
                        filtered_files.append(full_path)

        logger.info(f"Found {len(filtered_files)} valid files to index.")

        # Sequentially index files (could be parallelized)
        for f in filtered_files:
            await self.index_file(f, repo_id)

        logger.info("Full indexing complete.")
