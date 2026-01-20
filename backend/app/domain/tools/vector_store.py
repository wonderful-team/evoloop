
from sqlalchemy import delete, select

from app.core.config import settings
from app.domain.codebase.indexing.vectors.openai_embedder import OpenAIEmbedder
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import Tool
from app.logging import logger


class PGToolRetriever:
    """
    Retrieves tools using PostgreSQL pgvector extension.
    Replaces in-memory ToolRetriever for scalability.
    """

    def __init__(self):
        self.embedder = OpenAIEmbedder(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            model=settings.EMBEDDING_MODEL_NAME,
            dimensions=settings.EMBEDDING_DIMENSIONS
        )

    async def index_tool(self, tool_name: str, description: str, signature: str, category: str = None):
        """
        Index a single tool. Updates if exists.
        """
        # Generate embedding
        try:
            vector = await self.embedder.embed_query(signature)
        except Exception as e:
            logger.error(f"Failed to embed tool {tool_name}: {e}")
            return

        async with session_scope() as session:
            # Check if exists
            stmt = select(Tool).where(Tool.name == tool_name)
            result = await session.execute(stmt)
            existing_tool = result.scalar_one_or_none()

            if existing_tool:
                existing_tool.description = description
                existing_tool.signature = signature
                existing_tool.embedding = vector
                if category:
                    existing_tool.category = category
            else:
                new_tool = Tool(
                    name=tool_name,
                    description=description,
                    signature=signature,
                    embedding=vector,
                    category=category
                )
                session.add(new_tool)

            await session.commit()
            logger.debug(f"Indexed tool: {tool_name}")

    async def search_tools(self, query: str, k: int = 10) -> list[dict]:
        """
        Search for tools semantically. Returns list of dicts with tool info.
        """
        try:
            query_vector = await self.embedder.embed_query(query)
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            return []

        async with session_scope() as session:
            # pgvector KNN search
            # Order by embedding <-> query_vector
            stmt = select(Tool).order_by(Tool.embedding.cosine_distance(query_vector)).limit(k)
            result = await session.execute(stmt)
            tools = result.scalars().all()

            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "signature": t.signature
                }
                for t in tools
            ]

    async def clear_all(self):
        async with session_scope() as session:
            await session.execute(delete(Tool))
            await session.commit()

# Global Instance
pg_tool_retriever = PGToolRetriever()
