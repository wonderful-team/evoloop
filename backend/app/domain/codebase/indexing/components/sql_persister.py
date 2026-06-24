"""
SQLPersister: Handles SQL database persistence for indexed content.
"""
import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.codebase.indexing.components.content_indexer import IndexedContent
from app.models import (
    CodeChunk,
    CodeEntity,
    CodeRelation,
    SourceFile,
)

logger = logging.getLogger(__name__)


class SQLPersister:
    """
    Persists indexed content to SQL database:
    - CodeChunks (with embeddings)
    - CodeEntities
    - CodeRelations
    """

    async def clear_old_data(
        self,
        source_file: SourceFile,
        session: AsyncSession
    ):
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

    async def persist(
        self,
        indexed: IndexedContent,
        source_file: SourceFile,
        session: AsyncSession
    ) -> dict[str, int]:
        """
        Persist indexed content to SQL database.

        Returns:
            Mapping of entity full_name to entity ID for relation linking.
        """
        name_to_id = await self.batch_persist(
            [(indexed, source_file)], session
        )
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
            for doc in indexed.documents:
                chunk = CodeChunk(
                    source_file_id=source_file.id,
                    chunk_type=doc.metadata.get("type", "unknown"),
                    identifier=doc.metadata.get("name", "unknown"),
                    start_line=doc.metadata.get("start_line", 0),
                    end_line=doc.metadata.get("end_line", 0),
                    content=doc.content,
                )
                session.add(chunk)

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

        # Build name_to_id maps and insert relations.
        all_name_to_ids: list[dict[str, int]] = []
        for indexed, records in staged:
            name_to_id = {}
            for ent, record in zip(indexed.entities, records, strict=False):
                name_to_id[ent.full_name] = record.id

            for rel in indexed.relations:
                source_id = name_to_id.get(rel.source_full_name)
                if not source_id:
                    continue
                target_id = name_to_id.get(rel.target_full_name)
                rel_record = CodeRelation(
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    target_name=rel.target_full_name,
                    relation_type=rel.relation_type,
                )
                session.add(rel_record)

            all_name_to_ids.append(name_to_id)

        return all_name_to_ids
