"""
Knowledge base vector semantic search service (T-3.1).

Integrates LanceDB vector storage with document chunking and embeddings
for semantic search over knowledge base documents.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from app.infrastructure.database.vector import BaseVectorStore, get_vector_store

logger = logging.getLogger(__name__)


class KBVectorSearchService:
    """
    Semantic vector search for knowledge base documents.

    Usage:
        service = KBVectorSearchService()
        await service.index_document(
            doc_id="collection/doc.md",
            title="Document Title",
            content="full content...",
            collection="myapp",
            tags=["api", "auth"]
        )

        results = await service.search("authentication methods", collection="myapp", top_k=5)
    """

    def __init__(self, vector_store: Optional[BaseVectorStore] = None):
        self.vector_store = vector_store or get_vector_store()
        self._embedder = None

    async def _get_embedder(self):
        """Lazy-load embedder."""
        if self._embedder is None:
            from app.infrastructure.embeddings.factory import EmbedderFactory
            self._embedder = EmbedderFactory.get_embedder()
        return self._embedder

    @staticmethod
    def _chunk_document(content: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
        """Simple sliding-window chunking with natural break points."""
        if not content:
            return []

        chunks = []
        start = 0
        content_len = len(content)

        while start < content_len:
            end = min(start + chunk_size, content_len)

            # Try to break at natural boundaries if not at end
            if end < content_len:
                for sep in ["\n\n", "\n", ". ", " "]:
                    pos = content.rfind(sep, start, end)
                    if pos > start:
                        end = pos + len(sep)
                        break

            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= content_len:
                break

            start = end - overlap
            if start >= end:
                start = end

        return chunks

    async def index_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        collection: str = "default",
        tags: Optional[list[str]] = None,
    ) -> int:
        """
        Chunk, embed, and index a document for semantic search.

        Args:
            doc_id: Unique document identifier (e.g. collection/path)
            title: Document title
            content: Full document content
            collection: Collection name
            tags: List of tags

        Returns:
            Number of chunks indexed
        """
        try:
            embedder = await self._get_embedder()
            chunks = self._chunk_document(content)

            if not chunks:
                return 0

            embeddings = await embedder.embed_documents(chunks)

            records = []
            for i, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
                records.append({
                    "id": f"{doc_id}:{i}",
                    "vector": emb,
                    "content": chunk_text,
                    "source_type": "kb",
                    "source_id": doc_id,
                    "title": title,
                    "chunk_index": i,
                    "collection": collection,
                    "tags": ",".join(tags or []),
                    "created_at": datetime.utcnow(),
                })

            await asyncio.to_thread(self.vector_store.upsert_kb_chunks, records)
            return len(records)

        except Exception as e:
            logger.warning(f"Failed to vector-index document {doc_id}: {e}")
            return 0

    async def search(
        self,
        query: str,
        collection: Optional[str] = None,
        top_k: int = 10,
    ) -> list[dict]:
        """
        Semantic search over knowledge base chunks.

        Args:
            query: Natural language query
            collection: Filter by collection
            top_k: Maximum results

        Returns:
            List of results with content, doc_id, title, score
        """
        try:
            embedder = await self._get_embedder()
            query_vector = await embedder.embed_query(query)
            return await asyncio.to_thread(
                self.vector_store.search_kb,
                query_vector=query_vector,
                top_k=top_k,
                collection=collection,
            )
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []

    def delete_document(self, doc_id: str) -> int:
        """Remove all vector chunks for a document."""
        return self.vector_store.delete_kb_by_doc(doc_id)


# Singleton instance
_kb_vector_service: Optional[KBVectorSearchService] = None


def get_kb_vector_service(vector_store: Optional[BaseVectorStore] = None) -> KBVectorSearchService:
    """Get or create KB vector search service singleton."""
    global _kb_vector_service
    if _kb_vector_service is None:
        _kb_vector_service = KBVectorSearchService(vector_store=vector_store)
    return _kb_vector_service
