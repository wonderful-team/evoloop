"""
MeilisearchBackend — Production-mode full-text search using Meilisearch.

Features:
- Built-in Chinese tokenization (jieba)
- BM25 ranking
- Typo tolerance
- Faceted search
- Highlighting
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.infrastructure.search.base import (
    IndexDocumentRequest,
    KnowledgeSearchResult,
    ReindexResult,
    SearchIndexStats,
    SearchResults,
    SearchSuggestion,
)

logger = logging.getLogger(__name__)

INDEX_NAME = "kb_documents"


class MeilisearchBackend:
    """Meilisearch implementation of SearchBackend."""

    def __init__(self):
        self._client = None
        self._index = None

    def _get_client(self):
        if self._client is None:
            try:
                from meilisearch import Client
            except ImportError:
                raise ImportError(
                    "meilisearch-python is not installed. "
                    "Install with: pip install meilisearch"
                )
            self._client = Client(
                settings.MEILISEARCH_URL,
                settings.MEILISEARCH_API_KEY or None,
            )
            self._index = self._client.index(INDEX_NAME)
        return self._client, self._index

    async def initialize(self) -> None:
        """Ensure the Meilisearch index exists and is configured."""
        client, index = self._get_client()
        try:
            # Check if index exists
            client.get_index(INDEX_NAME)
            logger.info(f"[MeilisearchBackend] Index '{INDEX_NAME}' already exists")
        except Exception:
            # Create index
            client.create_index(INDEX_NAME, {"primaryKey": "id"})
            logger.info(f"[MeilisearchBackend] Created index '{INDEX_NAME}'")

        # Update searchable attributes
        index.update_searchable_attributes(
            ["title", "content", "tags", "path"]
        )
        # Update filterable attributes
        index.update_filterable_attributes(
            ["collection", "tags"]
        )
        # Update sortable attributes
        index.update_sortable_attributes(
            ["indexed_at"]
        )
        # Update ranking rules (BM25 is default)
        index.update_ranking_rules(
            [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ]
        )
        logger.info("[MeilisearchBackend] Index settings updated")

    # -- document operations -----------------------------------------------

    async def index_document(self, request: IndexDocumentRequest) -> bool:
        try:
            _, index = self._get_client()
            doc = {
                "id": request.doc_id,
                "path": request.path,
                "collection": request.collection,
                "title": request.title,
                "content": request.content[:50000],  # Meilisearch has size limits
                "tags": ",".join(request.tags or []),
                "file_size": request.file_size or 0,
                "word_count": request.word_count or 0,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }
            index.add_documents([doc], primary_key="id")
            return True
        except Exception as e:
            logger.error(f"[MeilisearchBackend] Failed to index {request.doc_id}: {e}")
            return False

    async def remove_document(self, doc_id: str) -> bool:
        try:
            _, index = self._get_client()
            index.delete_document(doc_id)
            return True
        except Exception as e:
            logger.error(f"[MeilisearchBackend] Failed to remove {doc_id}: {e}")
            return False

    # -- search ------------------------------------------------------------

    async def search(
        self,
        query: str,
        collection: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResults:
        _, index = self._get_client()

        filters: list[str] = []
        if collection:
            filters.append(f"collection = '{collection}'")
        if tags:
            # Meilisearch IN operator: tags IN [tag1, tag2]
            # But tags is stored as comma-separated string, not array.
            # For simplicity, we use OR conditions.
            tag_filters = [f"tags = '{t}'" for t in tags]
            filters.append(f"({' OR '.join(tag_filters)})")

        filter_str = " AND ".join(filters) if filters else None

        try:
            result = index.search(
                query,
                {
                    "limit": limit,
                    "offset": offset,
                    "filter": filter_str,
                    "attributesToHighlight": ["content", "title"],
                    "highlightPreTag": "<mark>",
                    "highlightPostTag": "</mark>",
                    "attributesToRetrieve": [
                        "id",
                        "path",
                        "collection",
                        "title",
                        "content",
                        "tags",
                    ],
                },
            )
        except Exception as e:
            logger.error(f"[MeilisearchBackend] Search failed: {e}")
            return SearchResults(query=query, total=0, results=[], facets={})

        results = []
        for hit in result.get("hits", []):
            highlights = hit.get("_formatted", {})
            title_highlight = highlights.get("title", hit.get("title", ""))
            content_highlight = highlights.get("content", "")
            snippet = content_highlight[:300] + "..." if len(content_highlight) > 300 else content_highlight
            results.append(
                KnowledgeSearchResult(
                    doc_id=hit["id"],
                    path=hit.get("path", hit["id"]),
                    collection=hit.get("collection", "default"),
                    title=hit.get("title", ""),
                    content_snippet=snippet,
                    highlights=title_highlight if title_highlight != hit.get("title", "") else snippet,
                    rank=0.0,
                    bm25_score=0.0,
                )
            )

        facets = await self._get_facets(query, collection)
        return SearchResults(
            query=query,
            total=result.get("estimatedTotalHits", 0),
            results=results,
            facets=facets,
        )

    async def _get_facets(
        self, query: str, project_filter: Optional[str]
    ) -> dict:
        _, index = self._get_client()
        facets: dict = {"collections": {}, "tags": {}}
        try:
            # Meilisearch facet search
            facet_result = index.search(
                query,
                {
                    "limit": 0,
                    "facets": ["collection"],
                    "filter": f"collection = '{project_filter}'" if project_filter else None,
                },
            )
            facet_distribution = facet_result.get("facetDistribution", {})
            facets["collections"] = facet_distribution.get("collection", {})
        except Exception:
            pass
        return facets

    async def suggest(
        self,
        prefix: str,
        collection: Optional[str] = None,
        limit: int = 10,
    ) -> list[SearchSuggestion]:
        _, index = self._get_client()
        suggestions: list[SearchSuggestion] = []
        try:
            filter_str = f"collection = '{collection}'" if collection else None
            result = index.search(
                prefix,
                {
                    "limit": limit,
                    "filter": filter_str,
                    "attributesToRetrieve": ["title", "path"],
                },
            )
            for hit in result.get("hits", []):
                suggestions.append(
                    SearchSuggestion(
                        text=hit.get("title", ""),
                        path=hit.get("path"),
                        type="title",
                    )
                )
        except Exception as e:
            logger.warning(f"[MeilisearchBackend] Suggest failed: {e}")
        return suggestions[:limit]

    async def list_tags(
        self,
        collection: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        # Meilisearch doesn't have a native tag list API.
        # Fallback to aggregation via search.
        _, index = self._get_client()
        tags: list[dict] = []
        try:
            filter_str = f"collection = '{collection}'" if collection else None
            result = index.search(
                "",
                {
                    "limit": 1000,
                    "filter": filter_str,
                    "facets": ["tags"],
                },
            )
            facet_distribution = result.get("facetDistribution", {})
            tags = [
                {"name": tag, "count": count}
                for tag, count in facet_distribution.get("tags", {}).items()
            ]
            tags.sort(key=lambda x: x["count"], reverse=True)
        except Exception as e:
            logger.warning(f"[MeilisearchBackend] list_tags failed: {e}")
        return tags[:limit], len(tags)

    async def get_tag_config(self) -> list[dict]:
        # Tag config is stored locally (not in Meilisearch)
        # For now, return empty list. Can be stored in main DB later.
        return []

    async def update_tag_config(
        self,
        tag: str,
        category: str = "type",
        enabled: bool = True,
        priority: int = 0,
        description: str = "",
    ) -> bool:
        # Tag config is stored locally
        return True

    async def get_stats(self) -> SearchIndexStats:
        _, index = self._get_client()
        try:
            stats = index.get_stats()
            total_documents = stats.get("numberOfDocuments", 0)
            # Collections are not directly available in Meilisearch stats
            # We could scan all documents, but that's expensive.
            return SearchIndexStats(
                total_documents=total_documents,
                total_terms=0,
                collections=[],
                recent_searches=[],
            )
        except Exception as e:
            logger.warning(f"[MeilisearchBackend] get_stats failed: {e}")
            return SearchIndexStats(
                total_documents=0, total_terms=0, collections=[], recent_searches=[]
            )

    async def reindex_all(self, store_service) -> ReindexResult:
        _, index = self._get_client()
        # Delete all existing documents
        try:
            index.delete_all_documents()
        except Exception as e:
            logger.warning(f"[MeilisearchBackend] Failed to clear index: {e}")

        documents = store_service.list_documents()
        indexed = 0
        failed = 0
        batch: list[dict] = []
        BATCH_SIZE = 100

        for doc in documents:
            try:
                result = store_service.read_document(doc.path)
                content = result.content
                title = doc.title or doc.path.split("/")[-1]
                collection = doc.path.split("/")[0] if "/" in doc.path else "default"
                batch.append(
                    {
                        "id": doc.path,
                        "path": doc.path,
                        "collection": collection,
                        "title": title,
                        "content": content[:50000],
                        "tags": "",
                        "file_size": doc.size_bytes,
                        "word_count": len(content.split()),
                    }
                )
                if len(batch) >= BATCH_SIZE:
                    index.add_documents(batch, primary_key="id")
                    indexed += len(batch)
                    batch = []
            except Exception as e:
                logger.error(f"Failed to index {doc.path}: {e}")
                failed += 1

        if batch:
            index.add_documents(batch, primary_key="id")
            indexed += len(batch)

        return ReindexResult(indexed=indexed, failed=failed, total=len(documents))

    def close(self) -> None:
        # Meilisearch Python client is stateless (HTTP), nothing to close.
        pass
