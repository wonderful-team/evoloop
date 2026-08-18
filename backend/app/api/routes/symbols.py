from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser, get_db
from app.api.schemas.symbols import SymbolRelationResponse, SymbolResponse
from app.models import CodeEntity, Repository

router = APIRouter()


@router.get("/projects/{project_id}/symbols", response_model=list[SymbolResponse])
async def search_symbols(
    project_id: int,
    q: str = Query(..., min_length=2, description="Search query for symbol name"),
    type: str | None = Query(None, description="Filter by entity type (class, function)"),
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: CurrentUser = None,  # noqa: ARG001
):
    """
    Search for code symbols (classes, functions) within a project.
    """
    # 1. Find Repositories for Project (Assuming simple mapping via project_id column in Repository)
    # Note: In new model project_id is just an integer in Repository table.

    stmt = select(Repository.id).where(Repository.project_id == project_id)
    result = db.execute(stmt)
    repo_ids = result.scalars().all()

    if not repo_ids:
        # Maybe project has no repos or invalid project? Return empty for now.
        return []

    # 2. Search CodeEntities
    # Join with SourceFile to filter by repo_ids
    from sqlalchemy.orm import selectinload

    from app.models import SourceFile

    query = (
        select(CodeEntity)
        .join(SourceFile, CodeEntity.file_id == SourceFile.id)
        .where(SourceFile.repository_id.in_(repo_ids))
        .where(CodeEntity.full_name.ilike(f"%{q}%"))
        .options(selectinload(CodeEntity.file))
    )

    if type:
        query = query.where(CodeEntity.type == type)

    query = query.limit(limit)

    result = db.execute(query)
    entities = result.scalars().all()

    # 3. Format Response
    response = []
    for ent in entities:
        response.append(SymbolResponse(
            id=ent.id,
            name=ent.name,
            full_name=ent.full_name,
            type=ent.type,
            file_path=ent.file.path, # Lazy load might trigger query, async accessible?
            # Warning: accessing relationship in async loop without selectinload might fail or be slow.
            # Ideally we should use selectinload(CodeEntity.file) in the query.
            # Let's fix query options.
            start_line=ent.start_line,
            end_line=ent.end_line
        ))

    return response


@router.get("/projects/{project_id}/relations", response_model=list[SymbolRelationResponse])
async def get_project_relations(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = None,  # noqa: ARG001
):
    """
    Get all dependency relationships (CodeRelations) within a project.
    """
    from app.models import CodeRelation, SourceFile

    # 1. Find Repositories for Project
    stmt = select(Repository.id).where(Repository.project_id == project_id)
    result = db.execute(stmt)
    repo_ids = result.scalars().all()

    if not repo_ids:
        return []

    # 2. Query relations with eager loaded entities and source files
    query = select(CodeRelation)\
        .join(CodeEntity, CodeRelation.source_entity_id == CodeEntity.id)\
        .join(SourceFile, CodeEntity.file_id == SourceFile.id)\
        .where(SourceFile.repository_id.in_(repo_ids))\
        .options(
            selectinload(CodeRelation.source_entity).selectinload(CodeEntity.file),
            selectinload(CodeRelation.target_entity).selectinload(CodeEntity.file)
        )

    result = db.execute(query)
    relations = result.scalars().all()

    # 3. Format Response
    response = []
    for rel in relations:
        source = rel.source_entity
        target = rel.target_entity

        # Determine source and target paths
        source_path = source.file.path if (source and source.file) else ""
        target_path = target.file.path if (target and target.file) else None

        response.append(SymbolRelationResponse(
            id=rel.id,
            source_id=rel.source_entity_id,
            target_id=rel.target_entity_id,
            source_name=source.name if source else "",
            target_name=target.name if target else rel.target_name,
            relation_type=rel.relation_type,
            source_file_path=source_path,
            target_file_path=target_path
        ))

    return response
