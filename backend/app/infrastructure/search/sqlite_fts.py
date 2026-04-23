"""
SQLiteFTSBackend — Embedded-mode full-text search using SQLite FTS5.

This replaces the legacy FTSService in domain/knowledge/services/search.py.
All logic is preserved; only the surrounding interface is unified.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.domain.knowledge.services.connection_pool import KnowledgeConnectionPool
from app.infrastructure.search.base import (
    IndexDocumentRequest,
    KnowledgeSearchResult,
    ReindexResult,
    SearchIndexStats,
    SearchResults,
    SearchSuggestion,
)

logger = logging.getLogger(__name__)


class SQLiteFTSBackend:
    """SQLite FTS5 implementation of SearchBackend."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or settings.SEARCH_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.pool = KnowledgeConnectionPool(self.db_path)

    async def initialize(self) -> None:
        """Ensure FTS tables and auxiliary tables exist."""
        with self.pool.acquire() as conn:
            # FTS5 virtual table
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_documents USING fts5(
                    doc_id,
                    path,
                    collection,
                    title,
                    content,
                    tags,
                    tokenize='porter unicode61'
                )
                """
            )

            # Metadata table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS doc_metadata (
                    doc_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    collection TEXT NOT NULL DEFAULT 'default',
                    title TEXT,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_size INTEGER,
                    word_count INTEGER
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_project ON doc_metadata(collection)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_path ON doc_metadata(path)"
            )

            # Tags
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS doc_tags (
                    doc_id TEXT,
                    tag TEXT,
                    PRIMARY KEY (doc_id, tag)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tag ON doc_tags(tag)")

            # Search history
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    results_count INTEGER,
                    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id TEXT
                )
                """
            )

            # Tag config
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tag_config (
                    tag TEXT PRIMARY KEY,
                    category TEXT NOT NULL DEFAULT 'type',
                    enabled BOOLEAN DEFAULT 1,
                    priority INTEGER DEFAULT 0,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tag_config_category ON tag_config(category)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tag_config_enabled ON tag_config(enabled)"
            )

            conn.commit()
            logger.info(f"[SQLiteFTSBackend] Initialized at {self.db_path}")

    # -- document operations -----------------------------------------------

    async def index_document(self, request: IndexDocumentRequest) -> bool:
        try:
            with self.pool.acquire() as conn:
                conn.execute(
                    "DELETE FROM fts_documents WHERE doc_id = ?", (request.doc_id,)
                )
                conn.execute(
                    "DELETE FROM doc_metadata WHERE doc_id = ?", (request.doc_id,)
                )
                conn.execute(
                    "DELETE FROM doc_tags WHERE doc_id = ?", (request.doc_id,)
                )

                tags_str = ",".join(request.tags or [])
                conn.execute(
                    "INSERT INTO fts_documents (doc_id, path, collection, title, content, tags) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        request.doc_id,
                        request.path,
                        request.collection,
                        request.title,
                        request.content,
                        tags_str,
                    ),
                )
                conn.execute(
                    """INSERT INTO doc_metadata
                       (doc_id, path, collection, title, indexed_at, file_size, word_count)
                       VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)""",
                    (
                        request.doc_id,
                        request.path,
                        request.collection,
                        request.title,
                        request.file_size,
                        request.word_count,
                    ),
                )
                if request.tags:
                    conn.executemany(
                        "INSERT INTO doc_tags (doc_id, tag) VALUES (?, ?)",
                        [(request.doc_id, tag) for tag in request.tags],
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[SQLiteFTSBackend] Failed to index {request.doc_id}: {e}")
            return False

    async def remove_document(self, doc_id: str) -> bool:
        try:
            with self.pool.acquire() as conn:
                conn.execute("DELETE FROM fts_documents WHERE doc_id = ?", (doc_id,))
                conn.execute("DELETE FROM doc_metadata WHERE doc_id = ?", (doc_id,))
                conn.execute("DELETE FROM doc_tags WHERE doc_id = ?", (doc_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[SQLiteFTSBackend] Failed to remove {doc_id}: {e}")
            return False

    # -- search ------------------------------------------------------------

    def _preprocess_query(self, query: str) -> str:
        """Apply jieba segmentation for CJK queries (T-2.2)."""
        if not query or not query.strip():
            return query
        fts5_special_chars = {'"', '*', '(', ')', '^'}
        fts5_operators = {"AND", "OR", "NOT", "NEAR"}
        upper_q = query.upper()
        has_special = any(c in query for c in fts5_special_chars) or any(
            op in upper_q for op in fts5_operators
        )
        has_cjk = any(
            "\u4e00" <= c <= "\u9fff" or "\u3400" <= c <= "\u4dbf" for c in query
        )
        if has_cjk and not has_special:
            try:
                import jieba

                words = [w.strip() for w in jieba.cut(query.strip()) if w.strip()]
                if words:
                    phrases = []
                    for word in words:
                        cjk_chars = [
                            c
                            for c in word
                            if "\u4e00" <= c <= "\u9fff" or "\u3400" <= c <= "\u4dbf"
                        ]
                        if len(cjk_chars) > 1:
                            phrases.append('"' + " ".join(cjk_chars) + '"')
                        elif cjk_chars:
                            phrases.append(cjk_chars[0])
                        else:
                            phrases.append(word)
                    return " ".join(phrases)
            except Exception:
                logger.warning("jieba segmentation failed, falling back to raw query")
        return query

    async def search(
        self,
        query: str,
        collection: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResults:
        processed_query = self._preprocess_query(query)

        with self.pool.acquire() as conn:
            where_clauses = ["fts_documents MATCH ?"]
            join_clause = ""
            params: list = []

            if tags:
                tag_placeholders = ",".join(["?"] * len(tags))
                join_clause = f"""
                    JOIN (
                        SELECT doc_id FROM doc_tags
                        WHERE tag IN ({tag_placeholders})
                        GROUP BY doc_id
                        HAVING COUNT(DISTINCT tag) = ?
                    ) AS tag_filter ON fts_documents.doc_id = tag_filter.doc_id
                """
                params.extend(tags)
                params.append(len(tags))

            params.append(processed_query)
            if collection:
                where_clauses.append("fts_documents.collection = ?")
                params.append(collection)
            where_sql = " AND ".join(where_clauses)

            # Count
            count_sql = f"""
                SELECT COUNT(*) FROM fts_documents
                {join_clause}
                WHERE {where_sql}
            """
            total = conn.execute(count_sql, params).fetchone()[0]

            # Results
            search_sql = f"""
                SELECT
                    fts_documents.doc_id,
                    fts_documents.path,
                    fts_documents.collection,
                    fts_documents.title,
                    fts_documents.content,
                    bm25(fts_documents) as rank,
                    snippet(fts_documents, 4, '<mark>', '</mark>', '...', 32) as snippet
                FROM fts_documents
                {join_clause}
                WHERE {where_sql}
                ORDER BY rank ASC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            rows = conn.execute(search_sql, params).fetchall()

            results = []
            for row in rows:
                results.append(
                    KnowledgeSearchResult(
                        doc_id=row["doc_id"],
                        path=row["path"],
                        collection=row["collection"],
                        title=row["title"] or row["path"],
                        content_snippet=row["snippet"] or row["content"][:200] + "...",
                        highlights=row["snippet"] or "",
                        rank=row["rank"],
                        bm25_score=-row["rank"],
                    )
                )

            facets = await self._get_facets(processed_query, collection, conn)

            conn.execute(
                "INSERT INTO search_history (query, results_count) VALUES (?, ?)",
                (query, total),
            )
            conn.commit()

            return SearchResults(query=query, total=total, results=results, facets=facets)

    async def _get_facets(
        self, query: str, project_filter: Optional[str], conn: sqlite3.Connection
    ) -> dict:
        facets: dict = {"collections": {}, "tags": {}}
        sql = """
            SELECT collection, COUNT(*) as count
            FROM fts_documents
            WHERE fts_documents MATCH ?
            GROUP BY collection
        """
        params = [query]
        if project_filter:
            sql = sql.replace("GROUP BY", "AND collection = ? GROUP BY")
            params.append(project_filter)
        for row in conn.execute(sql, params):
            facets["collections"][row["collection"]] = row["count"]

        tag_sql = """
            SELECT dt.tag, COUNT(*) as count
            FROM doc_tags dt
            JOIN fts_documents ft ON dt.doc_id = ft.doc_id
            WHERE ft.fts_documents MATCH ?
            GROUP BY dt.tag
            ORDER BY count DESC
            LIMIT 20
        """
        for row in conn.execute(tag_sql, [query]):
            facets["tags"][row["tag"]] = row["count"]
        return facets

    async def suggest(
        self,
        prefix: str,
        collection: Optional[str] = None,
        limit: int = 10,
    ) -> list[SearchSuggestion]:
        with self.pool.acquire() as conn:
            suggestions: list[SearchSuggestion] = []
            sql = "SELECT DISTINCT title, path FROM fts_documents WHERE title LIKE ? LIMIT ?"
            params = [f"%{prefix}%", limit]
            if collection:
                sql = sql.replace("WHERE", "WHERE collection = ? AND")
                params = [collection, f"%{prefix}%", limit]
            for row in conn.execute(sql, params):
                suggestions.append(
                    SearchSuggestion(text=row["title"], path=row["path"], type="title")
                )
            remaining = limit - len(suggestions)
            if remaining > 0:
                tag_sql = "SELECT DISTINCT tag FROM doc_tags WHERE tag LIKE ? LIMIT ?"
                for row in conn.execute(tag_sql, [f"%{prefix}%", remaining]):
                    suggestions.append(SearchSuggestion(text=row["tag"], type="tag"))
            return suggestions[:limit]

    async def list_tags(
        self,
        collection: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        with self.pool.acquire() as conn:
            if collection:
                sql = """
                    SELECT dt.tag, COUNT(*) as count
                    FROM doc_tags dt
                    JOIN doc_metadata dm ON dt.doc_id = dm.doc_id
                    WHERE dm.collection = ?
                    GROUP BY dt.tag
                    ORDER BY count DESC
                """
                params = [collection]
            else:
                sql = """
                    SELECT tag, COUNT(*) as count
                    FROM doc_tags
                    GROUP BY tag
                    ORDER BY count DESC
                """
                params = []
            tags = [{"name": row["tag"], "count": row["count"]} for row in conn.execute(sql, params)]
            total = len(tags)
            return tags[:limit], total

    async def get_tag_config(self) -> list[dict]:
        with self.pool.acquire() as conn:
            rows = conn.execute(
                """SELECT tag, category, enabled, priority, description
                   FROM tag_config
                   WHERE enabled = 1
                   ORDER BY category, priority DESC, tag"""
            ).fetchall()
            return [dict(row) for row in rows]

    async def update_tag_config(
        self,
        tag: str,
        category: str = "type",
        enabled: bool = True,
        priority: int = 0,
        description: str = "",
    ) -> bool:
        with self.pool.acquire() as conn:
            conn.execute(
                """INSERT INTO tag_config (tag, category, enabled, priority, description)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(tag) DO UPDATE SET
                       category = excluded.category,
                       enabled = excluded.enabled,
                       priority = excluded.priority,
                       description = excluded.description""",
                (tag, category, int(enabled), priority, description),
            )
            conn.commit()
            return True

    async def get_stats(self) -> SearchIndexStats:
        with self.pool.acquire() as conn:
            row = conn.execute("SELECT COUNT(*) FROM doc_metadata").fetchone()
            total_documents = row[0]
            collections = [
                row["collection"]
                for row in conn.execute(
                    "SELECT DISTINCT collection FROM doc_metadata ORDER BY collection"
                )
            ]
            recent_searches = [
                {"query": row["query"], "time": row["searched_at"]}
                for row in conn.execute(
                    "SELECT query, searched_at FROM search_history ORDER BY searched_at DESC LIMIT 10"
                )
            ]
            return SearchIndexStats(
                total_documents=total_documents,
                total_terms=0,
                collections=collections,
                recent_searches=recent_searches,
            )

    async def reindex_all(self, store_service) -> ReindexResult:
        with self.pool.acquire() as conn:
            conn.execute("DELETE FROM fts_documents")
            conn.execute("DELETE FROM doc_metadata")
            conn.execute("DELETE FROM doc_tags")
            conn.commit()

        documents = store_service.list_documents()
        indexed = 0
        failed = 0
        for doc in documents:
            try:
                result = store_service.read_document(doc.path)
                content = result.content
                title = doc.title or doc.path.split("/")[-1]
                collection = doc.path.split("/")[0] if "/" in doc.path else "default"
                await self.index_document(
                    IndexDocumentRequest(
                        doc_id=doc.path,
                        path=doc.path,
                        title=title,
                        content=content,
                        collection=collection,
                        file_size=doc.size_bytes,
                        word_count=len(content.split()),
                    )
                )
                indexed += 1
            except Exception as e:
                logger.error(f"Failed to index {doc.path}: {e}")
                failed += 1
        return ReindexResult(indexed=indexed, failed=failed, total=len(documents))

    def close(self) -> None:
        self.pool.close_all()
