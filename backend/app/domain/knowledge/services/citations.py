"""
Document citation tracking service.

Tracks which documents are referenced by the Agent and provides:
- Citation counts
- Last accessed time
- Popular documents
- Document relationships
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class CitationEvent(DynamicBaseModel):
    """A single citation event."""
    doc_id: str
    doc_path: str
    tool_used: str  # kb_read, kb_search, etc.
    session_id: Optional[str] = None
    agent_message: Optional[str] = None  # Context of the citation
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentStats(DynamicBaseModel):
    """Citation statistics for a document."""
    doc_id: str
    doc_path: str
    total_citations: int = 0
    unique_sessions: int = 0
    last_accessed: Optional[datetime] = None
    tools_used: dict[str, int] = Field(default_factory=dict)  # tool -> count
    related_docs: list[str] = Field(default_factory=list)  # docs often cited together


class UsageAnalytics(DynamicBaseModel):
    """Overall usage analytics."""
    period_days: int
    total_citations: int
    active_documents: int
    citations_by_tool: dict[str, int]
    popular_tags: list[str]
    most_cited: list[str]


class DocumentRecommendation(DynamicBaseModel):
    """Document recommendation based on citation patterns."""
    path: str
    reason: str
    relevance: float
    total_citations: int


class CitationTracker:
    """
    Track document citations by the Agent.
    
    Uses SQLite for persistence and provides analytics on document usage.
    
    Usage:
        tracker = CitationTracker()
        await tracker.initialize()
        
        # Record citation
        await tracker.record_citation(
            doc_path="collection/guide.md",
            tool_used="kb_read",
            session_id="sess_123"
        )
        
        # Get popular docs
        popular = await tracker.get_most_cited(limit=10)
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".evoloop" / "knowledge" / "citations.db"
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    async def initialize(self) -> None:
        """Initialize citation tables."""
        conn = self._get_connection()
        
        # Citation events
        conn.execute("""
            CREATE TABLE IF NOT EXISTS citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                doc_path TEXT NOT NULL,
                tool_used TEXT NOT NULL,
                session_id TEXT,
                agent_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Document statistics (materialized view for performance)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_stats (
                doc_id TEXT PRIMARY KEY,
                doc_path TEXT NOT NULL,
                total_citations INTEGER DEFAULT 0,
                unique_sessions INTEGER DEFAULT 0,
                last_accessed TIMESTAMP,
                tools_used TEXT,  -- JSON dict
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Session-document pairs for finding related docs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_docs (
                session_id TEXT,
                doc_id TEXT,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, doc_id)
            )
        """)
        
        # Indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_citations_doc ON citations(doc_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_citations_session ON citations(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_citations_time ON citations(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session_docs_session ON session_docs(session_id)")
        
        conn.commit()
        logger.info(f"Citation tracker initialized at {self.db_path}")
    
    async def record_citation(
        self,
        doc_path: str,
        tool_used: str,
        session_id: Optional[str] = None,
        agent_message: Optional[str] = None
    ) -> bool:
        """
        Record a document citation.
        
        Args:
            doc_path: Document path
            tool_used: Tool that accessed the document (kb_read, kb_search, etc.)
            session_id: Optional session identifier
            agent_message: Optional context message
        
        Returns:
            True if recorded successfully
        """
        conn = self._get_connection()
        doc_id = doc_path  # Use path as ID
        
        try:
            # Record citation event
            conn.execute(
                """INSERT INTO citations 
                   (doc_id, doc_path, tool_used, session_id, agent_message)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc_id, doc_path, tool_used, session_id, agent_message[:500] if agent_message else None)
            )
            
            # Update session-docs mapping
            if session_id:
                conn.execute(
                    """INSERT OR REPLACE INTO session_docs (session_id, doc_id)
                       VALUES (?, ?)""",
                    (session_id, doc_id)
                )
            
            # Update document stats
            self._update_doc_stats(conn, doc_id, doc_path, tool_used)
            
            conn.commit()
            return True
        
        except Exception as e:
            logger.error(f"Failed to record citation: {e}")
            conn.rollback()
            return False
    
    def _update_doc_stats(
        self,
        conn: sqlite3.Connection,
        doc_id: str,
        doc_path: str,
        tool_used: str
    ) -> None:
        """Update materialized statistics for a document."""
        # Get current stats
        row = conn.execute(
            "SELECT * FROM doc_stats WHERE doc_id = ?",
            (doc_id,)
        ).fetchone()
        
        if row:
            # Update existing
            tools = json.loads(row["tools_used"] or "{}")
            tools[tool_used] = tools.get(tool_used, 0) + 1
            
            conn.execute(
                """UPDATE doc_stats 
                   SET total_citations = total_citations + 1,
                       last_accessed = CURRENT_TIMESTAMP,
                       tools_used = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE doc_id = ?""",
                (json.dumps(tools), doc_id)
            )
        else:
            # Create new
            tools = {tool_used: 1}
            conn.execute(
                """INSERT INTO doc_stats 
                   (doc_id, doc_path, total_citations, last_accessed, tools_used)
                   VALUES (?, ?, 1, CURRENT_TIMESTAMP, ?)""",
                (doc_id, doc_path, json.dumps(tools))
            )
        
        # Update unique sessions count
        conn.execute(
            """UPDATE doc_stats 
               SET unique_sessions = (
                   SELECT COUNT(DISTINCT session_id) 
                   FROM citations 
                   WHERE doc_id = ? AND session_id IS NOT NULL
               )
               WHERE doc_id = ?""",
            (doc_id, doc_id)
        )
    
    async def get_document_stats(self, doc_path: str) -> Optional[DocumentStats]:
        """Get citation statistics for a specific document."""
        conn = self._get_connection()
        
        row = conn.execute(
            "SELECT * FROM doc_stats WHERE doc_id = ?",
            (doc_path,)
        ).fetchone()
        
        if not row:
            return None
        
        # Get related documents (often cited together)
        related = await self._get_related_docs(doc_path)
        
        return DocumentStats(
            doc_id=row["doc_id"],
            doc_path=row["doc_path"],
            total_citations=row["total_citations"],
            unique_sessions=row["unique_sessions"],
            last_accessed=row["last_accessed"],
            tools_used=json.loads(row["tools_used"] or "{}"),
            related_docs=related
        )
    
    async def _get_related_docs(self, doc_path: str, limit: int = 5) -> list[str]:
        """Find documents often cited in same session."""
        conn = self._get_connection()
        
        # Find sessions that accessed this doc
        sessions = conn.execute(
            "SELECT DISTINCT session_id FROM session_docs WHERE doc_id = ?",
            (doc_path,)
        ).fetchall()
        
        if not sessions:
            return []
        
        session_ids = [s["session_id"] for s in sessions if s["session_id"]]
        if not session_ids:
            return []
        
        # Find other docs in same sessions
        placeholders = ",".join(["?"] * len(session_ids))
        rows = conn.execute(f"""
            SELECT doc_id, COUNT(*) as co_count
            FROM session_docs
            WHERE session_id IN ({placeholders})
              AND doc_id != ?
            GROUP BY doc_id
            ORDER BY co_count DESC
            LIMIT ?
        """, (*session_ids, doc_path, limit)).fetchall()
        
        return [row["doc_id"] for row in rows]
    
    async def get_most_cited(
        self,
        collection: Optional[str] = None,
        limit: int = 10,
        since: Optional[datetime] = None
    ) -> list[DocumentStats]:
        """
        Get most cited documents.
        
        Args:
            collection: Filter by collection (doc_path prefix)
            limit: Number of results
            since: Only count citations since this date
        """
        conn = self._get_connection()
        
        if since:
            # Query from citations table for time-filtered results
            sql = """
                SELECT 
                    doc_id,
                    doc_path,
                    COUNT(*) as total_citations,
                    COUNT(DISTINCT session_id) as unique_sessions,
                    MAX(created_at) as last_accessed
                FROM citations
                WHERE created_at >= ?
            """
            params = [since.isoformat()]
            
            if collection:
                sql += " AND doc_path LIKE ?"
                params.append(f"{collection}/%")
            
            sql += " GROUP BY doc_id ORDER BY total_citations DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(sql, params).fetchall()
        else:
            # Use materialized stats for better performance
            sql = "SELECT * FROM doc_stats"
            params = []
            
            if collection:
                sql += " WHERE doc_path LIKE ?"
                params.append(f"{collection}/%")
            
            sql += " ORDER BY total_citations DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(sql, params).fetchall()
        
        results = []
        for row in rows:
            tools = json.loads(row["tools_used"]) if "tools_used" in row.keys() else {}
            results.append(DocumentStats(
                doc_id=row["doc_id"],
                doc_path=row["doc_path"],
                total_citations=row["total_citations"],
                unique_sessions=row["unique_sessions"] if "unique_sessions" in row.keys() else 0,
                last_accessed=row["last_accessed"] if "last_accessed" in row.keys() else None,
                tools_used=tools,
                related_docs=[]
            ))
        
        return results
    
    async def get_usage_analytics(
        self,
        days: int = 30
    ) -> UsageAnalytics:
        """Get overall usage analytics."""
        conn = self._get_connection()

        since = datetime.now().replace(day=datetime.now().day - days)

        # Total citations in period
        row = conn.execute(
            "SELECT COUNT(*) as count FROM citations WHERE created_at >= ?",
            (since.isoformat(),)
        ).fetchone()
        total_citations = row["count"]

        # Citations by tool
        tool_stats: dict[str, int] = {}
        for row in conn.execute(
            """SELECT tool_used, COUNT(*) as count
               FROM citations
               WHERE created_at >= ?
               GROUP BY tool_used""",
            (since.isoformat(),)
        ):
            tool_stats[row["tool_used"]] = row["count"]

        # Active documents
        row = conn.execute(
            "SELECT COUNT(DISTINCT doc_id) as count FROM citations WHERE created_at >= ?",
            (since.isoformat(),)
        ).fetchone()
        active_docs = row["count"]

        # Popular tags (requires joining with FTS)
        # This is a placeholder - would need FTS integration
        popular_tags: list[str] = []

        return UsageAnalytics(
            period_days=days,
            total_citations=total_citations,
            active_documents=active_docs,
            citations_by_tool=tool_stats,
            popular_tags=popular_tags,
            most_cited=[s.doc_path for s in await self.get_most_cited(limit=5)]
        )
    
    async def get_recommendations(
        self,
        doc_path: str,
        limit: int = 5
    ) -> list[DocumentRecommendation]:
        """
        Get document recommendations based on citation patterns.

        Args:
            doc_path: Reference document
            limit: Number of recommendations

        Returns:
            List of recommended documents with relevance scores
        """
        recommendations: list[DocumentRecommendation] = []

        # Get related docs (co-cited)
        related = await self._get_related_docs(doc_path, limit)

        for rel_path in related:
            stats = await self.get_document_stats(rel_path)
            if stats:
                recommendations.append(DocumentRecommendation(
                    path=rel_path,
                    reason="often_cited_together",
                    relevance=min(stats.total_citations / 10, 1.0),  # Normalize
                    total_citations=stats.total_citations
                ))

        # Sort by relevance
        recommendations.sort(key=lambda x: x.relevance, reverse=True)
        return recommendations[:limit]
    
    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None


# Singleton instance
_tracker: Optional[CitationTracker] = None


def get_citation_tracker() -> CitationTracker:
    """Get or create citation tracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = CitationTracker()
    return _tracker
