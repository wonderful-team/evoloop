"""
SQLPersister: Handles SQL database persistence for indexed content.
"""

import logging

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.codebase.indexing.components.content_indexer import IndexedContent
from app.models import (
    CodeChunk,
    CodeEntity,
    CodeRelation,
    SourceFile,
)

logger = logging.getLogger(__name__)


def _extract_simple_name(target_name: str | None) -> str | None:
    """Return the simple symbol name from a possibly qualified target name."""
    if not target_name:
        return None
    # Strip FQN prefix "path/to/file.py::Class.method" -> "Class.method"
    name = target_name.split("::")[-1]
    # "a.b.c" -> "c"
    return name.split(".")[-1] or None


class SQLPersister:
    """
    Persists indexed content to SQL database:
    - CodeChunks (with embeddings)
    - CodeEntities
    - CodeRelations
    """

    async def clear_old_data(self, source_file: SourceFile, session: AsyncSession):
        """Clear existing chunks, entities, and relations for the file."""
        batch_file_ids = [source_file.id]
        await self._batch_clear(file_ids=batch_file_ids, session=session)

    async def batch_clear(
        self,
        source_files: list[SourceFile],
        session: AsyncSession,
    ):
        """Clear existing chunks, entities, and relations for multiple files."""
        file_ids = [sf.id for sf in source_files]
        await self._batch_clear(file_ids=file_ids, session=session)

    async def _batch_clear(
        self,
        file_ids: list[int],
        session: AsyncSession,
    ):
        """Common implementation: delete by file_ids."""
        from sqlalchemy import select

        # Delete relations via entity subquery
        entity_ids_subq = select(CodeEntity.id).where(CodeEntity.file_id.in_(file_ids))
        await session.execute(
            delete(CodeRelation).where(CodeRelation.source_entity_id.in_(entity_ids_subq))
        )

        # Delete entities
        await session.execute(
            delete(CodeEntity).where(CodeEntity.file_id.in_(file_ids))
        )

        # Delete chunks
        await session.execute(
            delete(CodeChunk).where(CodeChunk.source_file_id.in_(file_ids))
        )

    async def _resolve_cross_file_targets(
        self,
        session: AsyncSession,
        source_file_ids: list[int],
    ):
        """Resolve unresolved CodeRelation targets by searching CodeEntity names.

        For each relation with ``target_entity_id IS NULL`` and a non-empty
        ``target_name``, search the project's CodeEntity rows for a unique symbol
        match. If exactly one match is found, the target_entity_id is filled and
        confidence is set to ``INFERRED`` (graph-derived, not directly from AST).
        Otherwise confidence is set to
        ``AMBIGUOUS``.
        """
        if not source_file_ids:
            return

        # Build a repo-scoped entity lookup for all target names in this batch.
        unresolved_stmt = (
            select(CodeRelation, SourceFile.repository_id)
            .join(CodeEntity, CodeRelation.source_entity_id == CodeEntity.id)
            .join(SourceFile, CodeEntity.file_id == SourceFile.id)
            .where(SourceFile.id.in_(source_file_ids))
            .where(CodeRelation.target_entity_id.is_(None))
            .where(CodeRelation.target_name.isnot(None))
        )
        unresolved_result = await session.execute(unresolved_stmt)
        unresolved_rows = unresolved_result.all()
        if not unresolved_rows:
            return

        # Collect repo IDs and simple target names.
        repo_ids: set[int] = set()
        target_names: set[str] = set()
        for rel, repo_id in unresolved_rows:
            repo_ids.add(repo_id)
            simple_name = _extract_simple_name(rel.target_name)
            if simple_name:
                target_names.add(simple_name)

        if not target_names:
            # No resolvable names; mark all as AMBIGUOUS.
            for rel, _repo_id in unresolved_rows:
                rel.confidence = "AMBIGUOUS"
            return

        # Load candidate entities across the involved repos.
        candidates_stmt = (
            select(CodeEntity, SourceFile.repository_id)
            .join(SourceFile, CodeEntity.file_id == SourceFile.id)
            .where(SourceFile.repository_id.in_(repo_ids))
            .where(CodeEntity.name.in_(list(target_names)))
        )
        candidates_result = await session.execute(candidates_stmt)
        candidates = candidates_result.all()

        # Build (repo_id, name) -> list[CodeEntity] index.
        entity_index: dict[tuple[int, str], list[CodeEntity]] = {}
        for entity, repo_id in candidates:
            key = (repo_id, entity.name)
            entity_index.setdefault(key, []).append(entity)

        for rel, repo_id in unresolved_rows:
            simple_name = _extract_simple_name(rel.target_name)
            if not simple_name:
                rel.confidence = "AMBIGUOUS"
                continue

            matches = entity_index.get((repo_id, simple_name), [])
            if len(matches) == 1:
                rel.target_entity_id = matches[0].id
                rel.confidence = "INFERRED"
            else:
                rel.confidence = "AMBIGUOUS"

    async def persist(self, indexed: IndexedContent, source_file: SourceFile, session: AsyncSession) -> dict[str, int]:
        """
        Persist indexed content to SQL database.

        Returns:
            Mapping of entity full_name to entity ID for relation linking.
        """
        name_to_id = await self.batch_persist([(indexed, source_file)], session)
        return name_to_id[0] if name_to_id else {}

    async def batch_persist(
        self,
        items: list[tuple[IndexedContent, SourceFile]],
        session: AsyncSession,
    ) -> list[dict[str, int]]:
        """
        Persist multiple indexed contents in one session with a single flush.

        Returns list of name_to_id mappings (one per item).
        """
        staged: list[tuple[IndexedContent, list[CodeEntity]]] = []

        for indexed, source_file in items:
            records: list[CodeEntity] = []
            for ent in indexed.entities:
                record = CodeEntity(
                    file_id=source_file.id,
                    name=ent.name,
                    type=ent.type,
                    full_name=ent.full_name,
                    start_line=ent.start_line,
                    end_line=ent.end_line,
                )
                session.add(record)
                records.append(record)

            staged.append((indexed, records))

        # Single flush for all entity IDs.
        await session.flush()

        # Bulk insert chunks (no RETURNING needed).
        chunk_dicts = []
        for indexed, source_file in items:
            for doc in indexed.documents:
                chunk_dicts.append({
                    "source_file_id": source_file.id,
                    "chunk_type": doc.metadata.get("type", "unknown"),
                    "identifier": doc.metadata.get("name", "unknown"),
                    "start_line": doc.metadata.get("start_line", 0),
                    "end_line": doc.metadata.get("end_line", 0),
                    "content": doc.content,
                })
        if chunk_dicts:
            await session.execute(insert(CodeChunk), chunk_dicts)

        # Build name_to_id maps and bulk insert relations.
        rel_dicts = []
        all_name_to_ids: list[dict[str, int]] = []
        for indexed, records in staged:
            name_to_id = {}
            for ent, record in zip(indexed.entities, records, strict=False):
                name_to_id[ent.full_name] = record.id

            for rel in indexed.relations:
                source_id = name_to_id.get(rel.source_full_name)
                if not source_id:
                    continue
                rel_dicts.append({
                    "source_entity_id": source_id,
                    "target_entity_id": name_to_id.get(rel.target_full_name),
                    "target_name": rel.target_full_name,
                    "relation_type": rel.relation_type,
                })

            all_name_to_ids.append(name_to_id)

        if rel_dicts:
            await session.execute(insert(CodeRelation), rel_dicts)

        # Resolve cross-file targets for the newly persisted relations.
        source_file_ids = [sf.id for _, sf in items]
        await self._resolve_cross_file_targets(session, source_file_ids)

        return all_name_to_ids
