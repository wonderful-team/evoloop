import logging
from typing import Any

from sqlalchemy import or_, select

from app.core.context.manager import ContextManager
from app.infrastructure.database import session_scope
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.models import (
    CodeEntity,
    CodeRelation,
    Repository,
    SourceFile,
)

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, embedder=None):
        self.session_factory = session_scope
        self.embedder = embedder or EmbedderFactory.get_embedder()

    async def search(
        self,
        query: str,
        operator: str,
        project_id: int = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        ctx_pid = ContextManager.current().project_id
        pid = project_id if project_id is not None else ctx_pid

        from app.domain.codebase.retrieval.hybrid import hybrid_searcher

        return await hybrid_searcher.search(query, project_id=pid, limit=limit, operator=operator)

    async def get_entity_relations(
        self, symbol_name: str, project_id: int = None
    ) -> dict[str, Any]:
        pid = self._resolve_pid(project_id)
        async with self.session_factory() as session:
            entity = await self._find_entity(session, symbol_name, pid)
            if not entity:
                return {"error": f"Symbol '{symbol_name}' not found."}

            outgoing, incoming = await self._load_relations(session, entity)
            return {
                "symbol": entity.full_name,
                "type": entity.type,
                "file": entity.file.path if entity.file else "unknown",
                "relations": {"outgoing": outgoing, "incoming": incoming},
            }

    async def find_symbol_definition(
        self, symbol_name: str, project_id: int = None, project_path: str | None = None
    ) -> list[dict[str, Any]]:
        pid = self._resolve_pid(project_id)
        async with self.session_factory() as session:
            entity = await self._find_entity(session, symbol_name, pid)
            if not entity:
                return []

            outgoing, _ = await self._load_relations(session, entity)
            return [
                {
                    "full_name": entity.full_name,
                    "type": entity.type,
                    "file_path": entity.file.path if entity.file else "unknown",
                    "outgoing": [o["target"] for o in outgoing],
                }
            ]

    async def find_usages(
        self, symbol_name: str, project_id: int = None
    ) -> list[dict[str, Any]]:
        pid = self._resolve_pid(project_id)
        async with self.session_factory() as session:
            entity = await self._find_entity(session, symbol_name, pid)
            if not entity:
                return []

            _, incoming = await self._load_relations(session, entity)
            return [{"source": i["source"], "type": i["type"]} for i in incoming]

    async def get_call_hierarchy(
        self, symbol_name: str, project_id: int = None
    ) -> dict[str, Any]:
        pid = self._resolve_pid(project_id)
        async with self.session_factory() as session:
            entity = await self._find_entity(session, symbol_name, pid)
            if not entity:
                return {"error": f"Symbol '{symbol_name}' not found."}

            outgoing, incoming = await self._load_relations(session, entity)

            async def _collect_calls(
                ent_id: int, direction: str, depth: int = 0
            ) -> list[dict]:
                if depth > 3:
                    return []
                results = []
                if direction == "out":
                    rows = (
                        await session.execute(
                            select(CodeRelation, CodeEntity)
                            .outerjoin(
                                CodeEntity,
                                CodeRelation.target_entity_id == CodeEntity.id,
                            )
                            .where(CodeRelation.source_entity_id == ent_id)
                        )
                    ).all()
                    for rel, target_ent in rows:
                        name = target_ent.full_name if target_ent else rel.target_name
                        entry = {"name": name, "type": rel.relation_type, "calls": []}
                        if target_ent:
                            entry["calls"] = await _collect_calls(target_ent.id, "out", depth + 1)
                        results.append(entry)
                else:
                    rows = (
                        await session.execute(
                            select(CodeRelation, CodeEntity)
                            .join(
                                CodeEntity,
                                CodeRelation.source_entity_id == CodeEntity.id,
                            )
                            .where(CodeRelation.target_entity_id == ent_id)
                        )
                    ).all()
                    for rel, source_ent in rows:
                        entry = {
                            "name": source_ent.full_name,
                            "type": rel.relation_type,
                            "called_by": [],
                        }
                        entry["called_by"] = await _collect_calls(
                            source_ent.id, "in", depth + 1
                        )
                        results.append(entry)
                return results

            return {
                "symbol": entity.full_name,
                "type": entity.type,
                "calls": outgoing,
                "called_by": incoming,
                "call_tree": await _collect_calls(entity.id, "out"),
            }

    async def multi_entity_query(
        self,
        entities: list[str],
        operator: str = "and",
        question: str = "",
        project_id: int = None,
    ) -> str:
        pid = self._resolve_pid(project_id)
        async with self.session_factory() as session:
            all_results = []
            for name in entities:
                entity = await self._find_entity(session, name, pid)
                if not entity:
                    all_results.append({"entity": name, "error": "not found"})
                    continue
                outgoing, incoming = await self._load_relations(session, entity)
                all_results.append({
                    "entity": entity.full_name,
                    "type": entity.type,
                    "file": entity.file.path if entity.file else "unknown",
                    "outgoing": outgoing,
                    "incoming": incoming,
                })

            if operator == "and":
                related = set()
                for r in all_results:
                    for o in r.get("outgoing", []):
                        related.add(o["target"])
                    for i in r.get("incoming", []):
                        related.add(i["source"])
                lines = [f"### {r['entity']} ({r['type']})" for r in all_results]
                lines.append(f"\n**Entities related to ALL of {entities}:** {', '.join(sorted(related)) if related else '(none)'}")
            else:
                lines = []
                for r in all_results:
                    if "error" in r:
                        lines.append(f"- {r['entity']}: {r['error']}")
                    else:
                        out_str = ", ".join(o["target"] for o in r.get("outgoing", [])[:10])
                        in_str = ", ".join(i["source"] for i in r.get("incoming", [])[:10])
                        parts = [
                            f"calls: [{out_str}]" if out_str else "",
                            f"called_by: [{in_str}]" if in_str else "",
                        ]
                        lines.append(f"- {r['entity']} ({r['type']}): {'; '.join(p for p in parts if p)}")

            return "\n".join(lines)

    # ---- helpers ----

    def _resolve_pid(self, project_id: int | None) -> int | None:
        ctx_pid = ContextManager.current().project_id
        return project_id if project_id is not None else ctx_pid

    async def _find_entity(self, session, name: str, pid: int | None) -> Any | None:
        stmt = select(CodeEntity).where(
            or_(CodeEntity.name == name, CodeEntity.full_name == name)
        )
        if pid:
            stmt = (
                stmt.join(SourceFile)
                .join(Repository)
                .where(Repository.project_id == pid)
            )
        stmt = stmt.limit(1)
        result = await session.execute(stmt)
        entity = result.scalar_one_or_none()
        if not entity:
            stmt = select(CodeEntity).where(CodeEntity.name.ilike(f"%{name}%"))
            if pid:
                stmt = (
                    stmt.join(SourceFile)
                    .join(Repository)
                    .where(Repository.project_id == pid)
                )
            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            entity = result.scalar_one_or_none()
        return entity

    async def _load_relations(self, session, entity) -> tuple[list[dict], list[dict]]:
        out_rows = (
            await session.execute(
                select(CodeRelation, CodeEntity)
                .outerjoin(CodeEntity, CodeRelation.target_entity_id == CodeEntity.id)
                .where(CodeRelation.source_entity_id == entity.id)
            )
        ).all()
        outgoing = []
        for rel, target_ent in out_rows:
            target_name = target_ent.full_name if target_ent else rel.target_name
            outgoing.append({"type": rel.relation_type, "target": target_name})

        in_rows = (
            await session.execute(
                select(CodeRelation, CodeEntity)
                .join(CodeEntity, CodeRelation.source_entity_id == CodeEntity.id)
                .where(CodeRelation.target_entity_id == entity.id)
            )
        ).all()
        incoming = []
        for rel, source_ent in in_rows:
            incoming.append({"source": source_ent.full_name, "type": rel.relation_type})

        return outgoing, incoming
