import logging

from sqlalchemy import text
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.infrastructure.config.service import SystemConfigService
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
            if provider in ["openai", "generic", "qwen"]:
                # Use settings dimensions or provider default
                embedder = GenericOpenAIEmbedder(
                    api_key=api_key or "dummy",
                    base_url=base_url,
                    model=model,
                    dimensions=settings.EMBEDDING_DIMENSIONS,
                )
            elif provider == "ollama":
                embedder = OllamaEmbedder(base_url=base_url, model=model)
            else:
                raise ValueError("Unknown provider")

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
        4. Triggers Re-indexing for current project.

        Note: Neo4j vector index operations are disabled in Client mode.
        Use Cloud API for graph-based concept storage.
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

        # 3. SQL Data Reset (Global)
        with Session(engine) as session:
            logger.warning("TRUNCATING code_chunks table...")
            session.exec(text("TRUNCATE TABLE code_chunks CASCADE"))

            # CRITICAL: Update column type to match new dimension
            # Postgres pgvector requires explicit cast or truncation (we truncated).
            logger.warning(f"ALTERING code_chunks embedding to VECTOR({new_dim})...")
            session.exec(text(f"ALTER TABLE code_chunks ALTER COLUMN embedding TYPE vector({new_dim}) USING embedding::vector({new_dim})"))

            session.commit()

            # Recreate Index? pgvector index works on column.
            # If we used ivfflat/hnsw with fixed dim, we might need to drop index.
            # Assuming standard index creation handled by alembic or manual,
            # for now we rely on the fact that the table is empty.
            # Ideally: DROP INDEX IF EXISTS code_chunks_embedding_idx;

        # 4. Trigger Reindexing (Lazy / Active)
        if current_project_id:
            # How to get repo id from project id?
            # We need a way to find the repo.
            # Repo is tied to project_id in SQL models.
            repo = None
            with Session(engine) as session:
                repo = session.exec(select(Repository).where(Repository.project_id == current_project_id)).first()

            if repo:
                logger.info(f"Emitting system.embedding_updated event for active project {current_project_id} (Repo {repo.id})")

                from app.core.events.base import BaseEvent, system_bus
                event = BaseEvent(
                    event_type="system.embedding_updated",
                    source="embedding_config",
                    data={"repo_id": repo.id, "project_id": current_project_id}
                )
                await system_bus.publish(event)
