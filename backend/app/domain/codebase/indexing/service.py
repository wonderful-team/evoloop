import glob
import os
from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.codebase.indexing.base import BaseEmbedder
from app.domain.codebase.indexing.extractors.treesitter_extractor import TreeSitterExtractor
from app.domain.codebase.indexing.vectors.factory import EmbedderFactory
from app.domain.project.service import project_context_manager
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.infrastructure.database.sql.models import Repository, SourceFile, CodeChunk, CodeEntity, CodeRelation
from app.logging import logger


class IndexingService:
    def __init__(self, session: AsyncSession = None):
        self.session_factory = AsyncSessionLocal
        # Note: Extractor now returns ExtractionResult
        self.extractor = TreeSitterExtractor()
        self.embedder: BaseEmbedder = EmbedderFactory.get_embedder()

    async def get_or_create_repo(self, path: str, name: str) -> Repository:
        async with self.session_factory() as session:
            # Check existing
            stmt = select(Repository).where(Repository.local_path == path)
            result = await session.execute(stmt)
            repo = result.scalars().first()

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

    async def index_file(self, file_path: str, repo_id: int, force: bool = False):
        """
        Index a single file. (Incremental update)
        Args:
           force: If True, ignore checksum and re-index.
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
                    from app.utils.file import read_file_content
                    # read_file_content returns (content, encoding)
                    content, _ = read_file_content(file_path)
                    if content is None: # utils returns empty string on failure currently, or raises? 
                         # My impl says: returns "", encoding and logs error.
                         # But wait, empty file is valid. 
                         # If exception caught inside, it returns "".
                         # We should probably trust it or check existence first.
                         # But wait, existing logic raised exception?
                         pass
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")
                    return

                # Checksum Verification
                # Checksum Verification
                from app.utils.hash import compute_md5
                new_checksum = compute_md5(content)

                # 1. Get or Create SourceFile (to check previous checksum)
                stmt = select(SourceFile).where(SourceFile.repository_id == repo_id, SourceFile.path == rel_path)
                result = await session.execute(stmt)
                source_file = result.scalars().first()

                if not force and source_file and source_file.checksum == new_checksum:
                    # logger.debug(f"Skipping {rel_path} (Unchanged)")
                    return

                # If we are here, it's new, modified, or forced
                logger.info(f"Indexing {rel_path} (Force={force}, Checksum mismatch or new)")

                # Extract
                extraction_result = await self.extractor.extract(file_path, content, module_path=rel_path)
                
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
                # COVERAGE FIX: Add a "whole_file" or "top_level" chunk to catch global variables/scripts
                # If file is reasonable size, add whole content. If huge, maybe just first 200 lines?
                # Let's target files < 30KB or just limit lines.
                
                # Logic: Always add a 'file' chunk, but cap the size to avoid token overflow in Embedder.
                # OpenAI Embedder limit is usually 8k tokens. 
                # Let's take first 300 lines or 15k chars as a safe "Context Summary" chunk.
                
                file_summary_content = content
                if len(content) > 15000:
                    file_summary_content = content[:15000] + "\n...(truncated)"
                
                # We create a pseudo-Document for this
                from app.domain.codebase.indexing.extractors.treesitter_extractor import Document
                summary_doc = Document(
                    content=file_summary_content,
                    metadata={
                       "type": "file",
                       "name": f"{rel_path}::whole_file",
                       "start_line": 1,
                       "end_line": getattr(source_file, 'lines', content.count('\n') + 1) # simple count if not tracked
                    }
                )
                
                # Prepend to docs so it's indexed
                docs.insert(0, summary_doc)
                
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
                        # 6.1 Sync File Node
                        # We store pg_id to link back to SQL if needed
                        await n4j.run("""
                            MERGE (f:File {path: $path, project_id: $pid}) 
                            SET f.last_indexed = timestamp(), f.pg_id = $pg_id
                        """, path=rel_path, pid=repo.project_id, pg_id=source_file.id)

                        # 6.2 Sync Code Entities and Relations
                        # This is a bit heavier, but necessary for Graph RAG/Analysis
                        
                        # First, we need to clear old entities/relations for this file?
                        # Since we use MERGE/DETACH logic, we might need a strategy.
                        # Strategy: Delete all CHILD nodes of this File first (to clear old functions/classes)
                        # Then recreate.
                        
                        await n4j.run("""
                            MATCH (f:File {path: $path, project_id: $pid})-[r:CONTAINS]->(e)
                            DETACH DELETE e
                        """, path=rel_path, pid=repo.project_id)
                        
                        # Now create new entities and link to File
                        for ent_name, ent_id in name_to_id.items():
                            # We need type info. Logic: we iterate entities list again to get type.
                            pass # loop below handles it

                        for ent in entities:
                            # Create Concept/Entity Node
                            # Label could be :CodeEntity, or specific like :Class, :Function
                            # Let's use generic :CodeEntity with type property for flexibility, 
                            # or multiple labels if Neo4j supports dynamic labels easily (Cypher specific).
                            # Let's stick to :CodeEntity.
                            await n4j.run("""
                                MATCH (f:File {path: $path, project_id: $pid})
                                MERGE (e:CodeEntity {full_name: $full_name, project_id: $pid})
                                ON CREATE SET e.name = $name, e.type = $type, e.pg_id = $ent_pg_id
                                ON MATCH SET e.name = $name, e.type = $type, e.pg_id = $ent_pg_id
                                MERGE (f)-[:CONTAINS]->(e)
                            """, path=rel_path, pid=repo.project_id, 
                                 name=ent.name, full_name=ent.full_name, type=ent.type,
                                 ent_pg_id=name_to_id.get(ent.full_name))

                        # 6.3 Sync Relations
                        # We need to link entities. Target might be in another file (not created yet).
                        # Graph Best Practice: create "Ghost Nodes" or just link by full_name if possible?
                        # Creating ghost nodes can pollute graph with duplicates if not managed carefully.
                        # Safer approach: Only link if target exists? No, that breaks order dependency.
                        # Better approach: MERGE on full_name constraint.
                        
                        # Note: We need a constraint on CodeEntity(full_name, project_id).
                        # Assuming schema setup handles constraints. If not, MERGE might be slow or duplicate.
                        # For now, we only link INTRA-FILE relations reliably, and Cross-File via MERGE (optimistic).
                        
                        for rel in relations:
                            if not rel.target_full_name: continue
                            
                            # Cypher to link Source -> Target
                            # We use MERGE for target to ensure it exists (even if ghost for now)
                            await n4j.run("""
                                MATCH (s:CodeEntity {full_name: $src_name, project_id: $pid})
                                MERGE (t:CodeEntity {full_name: $tgt_name, project_id: $pid})
                                MERGE (s)-[:RELATION {type: $rel_type}]->(t)
                            """, src_name=rel.source_full_name, tgt_name=rel.target_full_name, 
                                 pid=repo.project_id, rel_type=rel.relation_type)

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
                    # Cascade delete: File -> Entities
                    await n4j.run("""
                        MATCH (f:File {path: $path, project_id: $pid})
                        OPTIONAL MATCH (f)-[:CONTAINS]->(e)
                        DETACH DELETE e
                        DETACH DELETE f
                    """, path=rel_path, pid=repo.project_id)
            except Exception as e:
                logger.warning(f"Neo4j Delete Failed for {rel_path}: {e}")

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
        logger.info(f"Starting full indexing for repo {repo_id} at {repo_path} (Force={force})")
        
        from app.domain.codebase.filter import FileFilter
        from app.domain.codebase.ignore import GitignoreMatcher
        from app.constants import BLACKLIST_DIRS, DEFAULT_EXCLUDED_DIRS

        file_filter = FileFilter()
        ignore_matcher = GitignoreMatcher.from_file(repo_path, ".gitignore")

        # Walk directory
        filtered_files = []
        for root, dirs, files in os.walk(repo_path):
            # 1. Directory Filtering (Prune traversal)
            # We filter 'dirs' in-place.
            
            d_to_remove = []
            for d in dirs:
                full_d_path = os.path.join(root, d)
                
                # Check 1: Hardcoded Blacklist (Fastest)
                if d in BLACKLIST_DIRS or d.startswith('.'):
                     d_to_remove.append(d)
                     continue
                
                # Check 2: Gitignore (Flexible)
                if ignore_matcher.should_ignore(full_d_path, is_dir=True):
                    d_to_remove.append(d)
                    continue

            for d in d_to_remove:
                dirs.remove(d)

            for f in files:
                full_path = os.path.join(root, f)
                
                # Check 1: Gitignore
                if ignore_matcher.should_ignore(full_path, is_dir=False):
                    continue

                # Check 2: FileFilter (Binary, size, etc.)
                if file_filter.should_include(full_path):
                    # Check 3: Supported Extension for Indexing
                    valid_exts = (".py", ".js", ".ts", ".go", ".java", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".rs", ".php", ".rb", ".md")
                    if full_path.endswith(valid_exts):
                        filtered_files.append(full_path)

        logger.info(f"Found {len(filtered_files)} valid files to index (Applied .gitignore).")

        # Sequentially index files (could be parallelized)
        for f in filtered_files:
            await self.index_file(f, repo_id, force=force)

        logger.info("Full indexing complete.")
