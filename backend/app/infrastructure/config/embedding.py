import logging

from sqlmodel import Session, select

from app.core.config import settings
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.database.graph.driver import get_graph_db
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models import Repository

logger = logging.getLogger(__name__)


class EmbeddingConfigService:
    @staticmethod
    async def validate_connection(provider: str, base_url: str, model: str, api_key: str = None) -> tuple[bool, int]:
        """
        Pre-flight check: Validates that the embedder can actually embed text.
        """
        try:
            # We temporarily override factory logic by instantiating directly or using a temp override
            # Easier to just instantiate based on provider
            from app.infrastructure.embeddings.ollama import OllamaEmbedder
            from app.infrastructure.embeddings.openai import GenericOpenAIEmbedder

            embedder = None
            if provider == "ollama":
                # Ollama uses its own native API format
                embedder = OllamaEmbedder(base_url=base_url, model=model)
            else:
                # All other providers (openai, generic, qwen, lmstudio, vllm, etc.)
                # use OpenAI-compatible API format
                embedder = GenericOpenAIEmbedder(
                    api_key=api_key or "dummy",
                    base_url=base_url,
                    model=model,
                    dimensions=settings.EMBEDDING_DIMENSIONS,
                )

            # Test Embedding
            vec = await embedder.embed_query("test connection")
            if not vec or len(vec) == 0:
                raise ValueError("Empty embedding returned")

            return True, len(vec)  # Return success and dimension
        except Exception as e:
            logger.error(f"Embedding Validation Failed: {e}")
            raise e

    @staticmethod
    async def switch_embedding_model(
        provider: str,
        base_url: str,
        model: str,
        api_key: str = None,
        dimensions: int = None,
        current_project_id: int = None,
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
        _, validated_dim = await EmbeddingConfigService.validate_connection(provider, base_url, model, api_key)
        # Use provided dimensions or fall back to validated dimension
        new_dim = dimensions or validated_dim
        logger.info(f"New Embedding Model Validated. Dimension: {new_dim}")

        # 2. Update Config
        SystemConfigService.set_value("EMBEDDING_PROVIDER", provider)
        SystemConfigService.set_value("EMBEDDING_BASE_URL", base_url)
        SystemConfigService.set_value("EMBEDDING_MODEL", model)
        SystemConfigService.set_value("EMBEDDING_DIMENSIONS", str(new_dim))
        if api_key:
            SystemConfigService.set_value("EMBEDDING_API_KEY", api_key)

        # 3. Vector Data Reset (Global)
        from app.infrastructure.database.vector import get_vector_store

        vector_store = get_vector_store()
        logger.warning("Truncating all vector data due to embedding model change...")
        vector_store.truncate_all()

        # 4. Graph Reset & Migration
        from app.infrastructure.database.graph.driver import GraphManager
        driver = GraphManager.get_driver()
        
        # 4.1 Drop old index
        try:
            await driver.execute_query("DROP INDEX concept_embeddings IF EXISTS")
            logger.info("Dropped concept_embeddings index")
        except NotImplementedError:
            logger.debug("Graph Drop Index skipped (not supported in embedded mode)")
        except Exception as e:
            logger.warning(f"Graph Drop Index warning: {e}")

        # 4.2 Recreate Index via Schema Manager
        from app.infrastructure.database.graph.schema import schema_manager
        await schema_manager.initialize() 
        logger.info(f"Re-initialized Graph Schema with potential new dimensions")

        # 4.3 Migrate Concepts (Background-ish)
        await EmbeddingConfigService._migrate_neo4j_concepts(provider, base_url, model, api_key)

        # 5. Trigger Reindexing (Lazy / Active)
        if current_project_id:
            # How to get repo id from project id?
            # We need a way to find the repo.
            # Repo is tied to project_id in SQL models.
            repo = None
            with Session(db_resource_manager.sync_engine) as session:
                repo = session.exec(select(Repository).where(Repository.project_id == current_project_id)).first()

            if repo:
                logger.info(f"Emitting system.embedding_updated event for active project {current_project_id} (Repo {repo.id})")

                from app.core.events.publishers import publish_embedding_updated
                await publish_embedding_updated(repo.id, current_project_id)

    @staticmethod
    async def _migrate_neo4j_concepts(provider, base_url, model, api_key):
        """
        Iterates all Concepts, re-calculates embedding, updates node.
        """
        from app.infrastructure.database.graph.driver import GraphManager
        driver = GraphManager.get_driver()

        # Create a temporary embedder instance
        from app.infrastructure.embeddings.ollama import OllamaEmbedder
        from app.infrastructure.embeddings.openai import GenericOpenAIEmbedder

        embedder = None
        if provider == "ollama":
            embedder = OllamaEmbedder(base_url, model)
        else:
            embedder = GenericOpenAIEmbedder(
                api_key or "dummy",
                base_url,
                model,
                dimensions=settings.EMBEDDING_DIMENSIONS,
            )

        # Fetch all concepts - use portable ID retrieval
        query = "MATCH (c:Concept) RETURN c.name as name, c.description as desc, c.id as id"
        records = await driver.execute_query(query)

        logger.info(f"Migrating {len(records)} Graph Concepts having description...")

        for r in records:
            if not r.get('desc'): continue
            
            text_to_embed = f"{r['name']}: {r['desc']}"
            try:
                vec = await embedder.embed_query(text_to_embed)
                # Update via high-level API
                await driver.upsert_node("Concept", "id", {
                    "id": r["id"],
                    "embedding": vec
                })
            except Exception as e:
                logger.error(f"Failed to re-embed concept {r['name']}: {e}")
