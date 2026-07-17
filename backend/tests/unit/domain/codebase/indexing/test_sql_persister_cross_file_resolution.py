"""Tests for SQLPersister cross-file symbol resolution."""

import pytest
from sqlalchemy import select

from app.domain.codebase.indexing.components.sql_persister import SQLPersister
from app.infrastructure.database import session_scope
from app.models import CodeEntity, CodeRelation, Repository, SourceFile


async def _make_repo_and_file(path: str = "src/main.py"):
    async with session_scope() as db:
        repo = Repository(name="test-repo", url="local", sync_status="SYNCED")
        db.add(repo)
        await db.flush()

        source = SourceFile(
            repository_id=repo.id,
            path=path,
            checksum="0" * 64,
        )
        db.add(source)
        await db.flush()
        return repo.id, source.id


@pytest.mark.asyncio
async def test_resolve_cross_file_target_unique_match(_real_db):
    """Unique symbol match resolves target_entity_id and confidence EXTRACTED."""
    repo_id, source_file_id = await _make_repo_and_file()

    async with session_scope() as db:
        source_entity = CodeEntity(
            file_id=source_file_id,
            name="get_user",
            type="function",
            full_name="src.main.get_user",
            start_line=1,
            end_line=10,
        )
        target_entity = CodeEntity(
            file_id=source_file_id,
            name="fetch_user",
            type="function",
            full_name="src.utils.fetch_user",
            start_line=1,
            end_line=10,
        )
        db.add(source_entity)
        db.add(target_entity)
        await db.flush()

        rel = CodeRelation(
            source_entity_id=source_entity.id,
            target_entity_id=None,
            target_name="src.utils.fetch_user",
            relation_type="calls",
            confidence="INFERRED",
        )
        db.add(rel)
        await db.flush()

        persister = SQLPersister()
        await persister._resolve_cross_file_targets(db, [source_file_id])
        await db.flush()
        await db.refresh(rel)

        assert rel.target_entity_id == target_entity.id
        assert rel.confidence == "EXTRACTED"


@pytest.mark.asyncio
async def test_resolve_cross_file_target_ambiguous(_real_db):
    """Multiple symbol matches result in AMBIGUOUS confidence."""
    repo_id, source_file_id = await _make_repo_and_file()

    async with session_scope() as db:
        source_entity = CodeEntity(
            file_id=source_file_id,
            name="get_user",
            type="function",
            full_name="src.main.get_user",
            start_line=1,
            end_line=10,
        )
        db.add(source_entity)
        await db.flush()

        # Two targets with the same simple name "fetch_user" in different files.
        for path in ["src/utils.py", "src/helpers.py"]:
            target = SourceFile(
                repository_id=repo_id,
                path=path,
                checksum="0" * 64,
            )
            db.add(target)
            await db.flush()
            target_entity = CodeEntity(
                file_id=target.id,
                name="fetch_user",
                type="function",
                full_name=f"{path}::fetch_user",
                start_line=1,
                end_line=10,
            )
            db.add(target_entity)
            await db.flush()

        rel = CodeRelation(
            source_entity_id=source_entity.id,
            target_entity_id=None,
            target_name="fetch_user",
            relation_type="calls",
            confidence="INFERRED",
        )
        db.add(rel)
        await db.flush()

        persister = SQLPersister()
        await persister._resolve_cross_file_targets(db, [source_file_id])
        await db.flush()
        await db.refresh(rel)

        assert rel.target_entity_id is None
        assert rel.confidence == "AMBIGUOUS"


@pytest.mark.asyncio
async def test_batch_persist_resolves_cross_file_targets(_real_db):
    """batch_persist invokes cross-file resolution after inserting relations."""
    repo_id, source_file_id = await _make_repo_and_file()

    async with session_scope() as db:
        target_entity = CodeEntity(
            file_id=source_file_id,
            name="helper",
            type="function",
            full_name="src.main.helper",
            start_line=1,
            end_line=5,
        )
        db.add(target_entity)
        await db.flush()

    # Use a fake IndexedContent-like object to drive batch_persist.
    class FakeEntity:
        def __init__(self, name, type_, full_name, start, end):
            self.name = name
            self.type = type_
            self.full_name = full_name
            self.start_line = start
            self.end_line = end

    class FakeRelation:
        def __init__(self, source_full_name, target_full_name, relation_type):
            self.source_full_name = source_full_name
            self.target_full_name = target_full_name
            self.relation_type = relation_type

    class FakeIndexedContent:
        def __init__(self, entities, relations, documents=None):
            self.entities = entities
            self.relations = relations
            self.documents = documents or []

    async with session_scope() as db:
        source = await db.get(SourceFile, source_file_id)
        indexed = FakeIndexedContent(
            entities=[
                FakeEntity("main", "function", "src.main.main", 1, 10),
            ],
            relations=[
                FakeRelation("src.main.main", "src.main.helper", "calls"),
            ],
        )

        persister = SQLPersister()
        await persister.batch_persist([(indexed, source)], db)

        rel = (
            (await db.execute(select(CodeRelation).limit(1)))
            .scalars()
            .first()
        )
        assert rel is not None
        assert rel.confidence == "EXTRACTED"
        assert rel.target_entity_id is not None
