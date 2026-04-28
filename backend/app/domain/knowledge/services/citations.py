"""
Document citation tracking service — migrated to the main relational database.

Previously stored in a separate citations.db SQLite file.
Now uses SQLAlchemy ORM on the main database (SQLite or PostgreSQL).
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.citation import CitationEvent, DocStat, SessionDoc
from app.domain.knowledge.schemas import DocumentStats, DocumentRecommendation

logger = logging.getLogger(__name__)


class CitationTracker:
    """Track document citations by the Agent (SQLAlchemy ORM version)."""

    def __init__(self):
        self.engine = db_resource_manager.sync_engine

    async def initialize(self) -> None:
        """No-op: tables are created by DatabaseResourceManager."""
        pass

    def _session(self) -> Session:
        return Session(self.engine)

    async def record_citation(
        self,
        doc_path: str,
        tool_used: str,
        session_id: Optional[str] = None,
        agent_message: Optional[str] = None,
    ) -> bool:
        try:
            with self._session() as session:
                session.add(
                    CitationEvent(
                        doc_id=doc_path,
                        doc_path=doc_path,
                        tool_used=tool_used,
                        session_id=session_id,
                        agent_message=agent_message[:500] if agent_message else None,
                    )
                )
                if session_id:
                    session.merge(
                        SessionDoc(session_id=session_id, doc_id=doc_path)
                    )
                self._update_doc_stats(session, doc_path, doc_path, tool_used)
                session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to record citation: {e}")
            return False

    def _update_doc_stats(
        self, session: Session, doc_id: str, doc_path: str, tool_used: str
    ) -> None:
        stat = session.get(DocStat, doc_id)
        if stat:
            stat.total_citations += 1
            stat.last_accessed = datetime.utcnow()
            tools = json.loads(stat.tools_used or "{}")
            tools[tool_used] = tools.get(tool_used, 0) + 1
            stat.tools_used = json.dumps(tools)
        else:
            session.add(
                DocStat(
                    doc_id=doc_id,
                    doc_path=doc_path,
                    total_citations=1,
                    last_accessed=datetime.utcnow(),
                    tools_used=json.dumps({tool_used: 1}),
                )
            )

        session.flush()

        # Update unique_sessions count
        unique_count = session.scalar(
            select(func.count(func.distinct(CitationEvent.session_id)))
            .where(CitationEvent.doc_id == doc_id)
            .where(CitationEvent.session_id.isnot(None))
        )
        stat = session.get(DocStat, doc_id)
        if stat:
            stat.unique_sessions = unique_count or 0

    async def get_document_stats(self, doc_path: str) -> Optional[DocumentStats]:
        with self._session() as session:
            stat = session.get(DocStat, doc_path)
            if not stat:
                return None
            related = await self._get_related_docs(doc_path, session)
            return DocumentStats(
                doc_id=stat.doc_id,
                doc_path=stat.doc_path,
                total_citations=stat.total_citations,
                unique_sessions=stat.unique_sessions,
                last_accessed=stat.last_accessed,
                tools_used=json.loads(stat.tools_used or "{}"),
                related_docs=related,
            )

    async def _get_related_docs(
        self, doc_path: str, session: Session, limit: int = 5
    ) -> list[str]:
        sessions = session.execute(
            select(SessionDoc.session_id).where(SessionDoc.doc_id == doc_path)
        ).scalars().all()

        if not sessions:
            return []

        rows = session.execute(
            select(SessionDoc.doc_id, func.count().label("co_count"))
            .where(SessionDoc.session_id.in_(sessions))
            .where(SessionDoc.doc_id != doc_path)
            .group_by(SessionDoc.doc_id)
            .order_by(desc("co_count"))
            .limit(limit)
        ).all()

        return [row.doc_id for row in rows]

    async def get_most_cited(
        self,
        collection: Optional[str] = None,
        limit: int = 10,
        since: Optional[datetime] = None,
    ) -> list[DocumentStats]:
        with self._session() as session:
            if since:
                stmt = (
                    select(
                        CitationEvent.doc_id,
                        CitationEvent.doc_path,
                        func.count().label("total_citations"),
                        func.count(func.distinct(CitationEvent.session_id)).label(
                            "unique_sessions"
                        ),
                        func.max(CitationEvent.created_at).label("last_accessed"),
                    )
                    .where(CitationEvent.created_at >= since)
                    .group_by(CitationEvent.doc_id)
                    .order_by(desc("total_citations"))
                    .limit(limit)
                )
                if collection:
                    stmt = stmt.where(CitationEvent.doc_path.like(f"{collection}/%"))
                rows = session.execute(stmt).all()
            else:
                stmt = select(DocStat).order_by(desc(DocStat.total_citations)).limit(limit)
                if collection:
                    stmt = stmt.where(DocStat.doc_path.like(f"{collection}/%"))
                rows = session.execute(stmt).scalars().all()

            results = []
            for row in rows:
                if since:
                    results.append(
                        DocumentStats(
                            doc_id=row.doc_id,
                            doc_path=row.doc_path,
                            total_citations=row.total_citations,
                            unique_sessions=row.unique_sessions,
                            last_accessed=row.last_accessed,
                            tools_used={},
                            related_docs=[],
                        )
                    )
                else:
                    results.append(
                        DocumentStats(
                            doc_id=row.doc_id,
                            doc_path=row.doc_path,
                            total_citations=row.total_citations,
                            unique_sessions=row.unique_sessions,
                            last_accessed=row.last_accessed,
                            tools_used=json.loads(row.tools_used or "{}"),
                            related_docs=[],
                        )
                    )
            return results

    async def get_recommendations(
        self, doc_path: str, limit: int = 5
    ) -> list[DocumentRecommendation]:
        recommendations: list[DocumentRecommendation] = []
        with self._session() as session:
            related = await self._get_related_docs(doc_path, session, limit)
        for rel_path in related:
            stats = await self.get_document_stats(rel_path)
            if stats:
                recommendations.append(
                    DocumentRecommendation(
                        path=rel_path,
                        reason="often_cited_together",
                        relevance=min(stats.total_citations / 10, 1.0),
                        total_citations=stats.total_citations,
                    )
                )
        recommendations.sort(key=lambda x: x.relevance, reverse=True)
        return recommendations[:limit]


# Singleton instance
_tracker: Optional[CitationTracker] = None


def get_citation_tracker() -> CitationTracker:
    """Get or create citation tracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = CitationTracker()
    return _tracker
