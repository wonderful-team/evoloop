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
        # Delete chunks
        await session.execute(
            delete(CodeChunk).where(CodeChunk.source_file_id == source_file.id)
        )

        # Delete relations (using subquery)
        from sqlalchemy import select
        subq = select(CodeEntity.id).where(CodeEntity.file_id == source_file.id)
        await session.execute(
            delete(CodeRelation).where(CodeRelation.source_entity_id.in_(subq))
        )

        # Delete entities
        await session.execute(
            delete(CodeEntity).where(CodeEntity.file_id == source_file.id)
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
        # Insert chunks
        for doc, vector in zip(indexed.documents, indexed.embeddings, strict=False):
            chunk = CodeChunk(
                source_file_id=source_file.id,
                chunk_type=doc.metadata.get("type", "unknown"),
                identifier=doc.metadata.get("name", "unknown"),
                start_line=doc.metadata.get("start_line", 0),
                end_line=doc.metadata.get("end_line", 0),
                content=doc.content,
                embedding=vector,
            )
            session.add(chunk)

        # Insert entities and build name-to-id map
        name_to_id = {}
        for ent in indexed.entities:
            entity_record = CodeEntity(
                file_id=source_file.id,
                name=ent.name,
                type=ent.type,
                full_name=ent.full_name,
                start_line=ent.start_line,
                end_line=ent.end_line,
            )
            session.add(entity_record)
            await session.flush()
            name_to_id[ent.full_name] = entity_record.id

        # Insert relations
        for rel in indexed.relations:
            source_id = name_to_id.get(rel.source_full_name)
            if not source_id:
                continue

            target_id = name_to_id.get(rel.target_full_name)

            rel_record = CodeRelation(
                source_entity_id=source_id,
                target_entity_id=target_id,  # Can be None for cross-file
                target_name=rel.target_full_name,
                relation_type=rel.relation_type,
            )
            session.add(rel_record)

        return name_to_id
