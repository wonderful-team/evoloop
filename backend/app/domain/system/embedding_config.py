import logging
from sqlalchemy import text
from sqlmodel import Session, select
from app.core.db import engine
from app.domain.system.service import SystemConfigService
from app.domain.codebase.indexing.vectors.factory import EmbedderFactory
from app.infrastructure.database.graph.driver import get_graph_db
from app.domain.codebase.indexing.manager import indexing_manager

logger = logging.getLogger(__name__)

class EmbeddingConfigService:
    
    @staticmethod
    async def validate_connection(provider: str, base_url: str, model: str, api_key: str = None) -> bool:
        """
        Pre-flight check: Validates that the embedder can actually embed text.
        """
        try:
            # We temporarily override factory logic by instantiating directly or using a temp override
            # Easier to just instantiate based on provider
            from app.domain.codebase.indexing.vectors.openai_embedder import GenericOpenAIEmbedder
            from app.domain.codebase.indexing.vectors.ollama_embedder import OllamaEmbedder
            
            embedder = None
            if provider in ["openai", "generic", "qwen"]:
                embedder = GenericOpenAIEmbedder(api_key=api_key or "dummy", base_url=base_url, model=model)
            elif provider == "ollama":
                embedder = OllamaEmbedder(base_url=base_url, model=model)
            else:
                raise ValueError("Unknown provider")

            # Test Embedding
            vec = await embedder.embed_query("test connection")
            if not vec or len(vec) == 0:
                raise ValueError("Empty embedding returned")
            
            return True, len(vec) # Return success and dimension
        except Exception as e:
            logger.error(f"Embedding Validation Failed: {e}")
            raise e

    @staticmethod
    async def switch_embedding_model(
        provider: str, 
        base_url: str, 
        model: str, 
        api_key: str = None, 
        current_project_id: int = None
    ):
        """
        Critical Operation: Switches Embedding Model.
        1. Validates connection.
        2. Updates System Config.
        3. Truncates SQL Vector Data (Global).
        4. Resets Neo4j Vector Index.
        5. Migrates Neo4j Concepts (In-Place Re-embedding).
        6. Triggers Re-indexing for current project.
        """
        
        # 1. Validate
        _, new_dim = await EmbeddingConfigService.validate_connection(provider, base_url, model, api_key)
        logger.info(f"New Embedding Model Validated. Dimension: {new_dim}")

        # 2. Update Config
        SystemConfigService.set_value("EMBEDDING_PROVIDER", provider)
        SystemConfigService.set_value("EMBEDDING_BASE_URL", base_url)
        SystemConfigService.set_value("EMBEDDING_MODEL", model)
        if api_key:
            SystemConfigService.set_value("EMBEDDING_API_KEY", api_key)
            
        # 3. SQL Data Reset (Global)
        with Session(engine) as session:
            logger.warning("TRUNCATING code_chunks table...")
            session.exec(text("TRUNCATE TABLE code_chunks CASCADE"))
            session.commit()
            
            # Recreate Index? pgvector index works on column. 
            # If we used ivfflat/hnsw with fixed dim, we might need to drop index.
            # Assuming standard index creation handled by alembic or manual, 
            # for now we rely on the fact that the table is empty.
            # Ideally: DROP INDEX IF EXISTS code_chunks_embedding_idx;
        
        # 4. Neo4j Reset & Migration
        driver = await get_graph_db()
        async with driver.session() as session:
            # 4.1 Drop old index
            try:
                await session.run("DROP INDEX concept_embeddings IF EXISTS")
            except Exception as e:
                logger.warning(f"Neo4j Drop Index warning: {e}")
                
            # 4.2 Recreate Index with NEW Dimension
            try:
                await session.run(f"""
                    CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
                    FOR (c:Concept)
                    ON (c.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {new_dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                """)
            except Exception as e:
                logger.error(f"Failed to recreate Neo4j index: {e}")

            # 4.3 Migrate Concepts (Background-ish)
            # This might take time. Should be a background task? 
            # For now running inline or we delegate to background task in route.
            # We will just define the logic here.
            await EmbeddingConfigService._migrate_neo4j_concepts(provider, base_url, model, api_key)

        # 5. Trigger Reindexing (Lazy / Active)
        if current_project_id:
            # How to get repo id from project id? 
            # We need a way to find the repo.
            # Repo is tied to project_id in SQL models.
            repo = None
            with Session(engine) as session:
                from app.infrastructure.database.sql.models import Repository
                repo = session.exec(select(Repository).where(Repository.project_id == current_project_id)).first()
            
            if repo:
                logger.info(f"Triggering re-index for active project {current_project_id} (Repo {repo.id})")
                # Run in background via manager
                await indexing_manager.run_indexing_background(repo.id)
                # Note: The route handler should handle the background task dispatch. 
                # This service method prepares the state.

    @staticmethod
    async def _migrate_neo4j_concepts(provider, base_url, model, api_key):
        """
        Iterates all Concepts, re-calculates embedding, updates node.
        """
        driver = await get_graph_db()
        # Create a temporary embedder instance
        from app.domain.codebase.indexing.vectors.openai_embedder import GenericOpenAIEmbedder
        from app.domain.codebase.indexing.vectors.ollama_embedder import OllamaEmbedder
        
        embedder = None
        if provider == "ollama":
            embedder = OllamaEmbedder(base_url, model)
        else:
            embedder = GenericOpenAIEmbedder(api_key or "dummy", base_url, model)

        async with driver.session() as session:
            # Fetch all concepts
            result = await session.run("MATCH (c:Concept) RETURN c.name as name, c.description as desc, elementId(c) as id")
            records = await result.data()
            
            logger.info(f"Migrating {len(records)} Neo4j Concepts having description...")
            
            for r in records:
                text_to_embed = f"{r['name']}: {r['desc']}"
                try:
                    vec = await embedder.embed_query(text_to_embed)
                    # Update
                    await session.run(
                        "MATCH (c:Concept) WHERE elementId(c) = $id SET c.embedding = $vec",
                        id=r['id'], vec=vec
                    )
                except Exception as e:
                    logger.error(f"Failed to re-embed concept {r['name']}: {e}")
