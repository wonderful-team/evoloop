from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.api.deps import get_db
from app.infrastructure.database.sql.models import CodeEntity, Repository

router = APIRouter()

@router.get("/projects/{project_id}/symbols", response_model=List[dict])
async def search_symbols(
    project_id: int,
    q: str = Query(..., min_length=2, description="Search query for symbol name"),
    type: Optional[str] = Query(None, description="Filter by entity type (class, function)"),
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """
    Search for code symbols (classes, functions) within a project.
    """
    # 1. Find Repositories for Project (Assuming simple mapping via project_id column in Repository)
    # Note: In new model project_id is just an integer in Repository table.
    
    stmt = select(Repository.id).where(Repository.project_id == project_id)
    result = await db.execute(stmt)
    repo_ids = result.scalars().all()
    
    if not repo_ids:
        # Maybe project has no repos or invalid project? Return empty for now.
        return []

    # 2. Search CodeEntities
    # Join with SourceFile to filter by repo_ids
    from app.infrastructure.database.sql.models import SourceFile
    from sqlalchemy.orm import selectinload
    
    query = select(CodeEntity).join(SourceFile, CodeEntity.file_id == SourceFile.id)\
            .where(SourceFile.repository_id.in_(repo_ids))\
            .where(CodeEntity.full_name.ilike(f"%{q}%"))\
            .options(selectinload(CodeEntity.file))
            
    if type:
        query = query.where(CodeEntity.type == type)
        
    query = query.limit(limit)
    
    result = await db.execute(query)
    entities = result.scalars().all()
    
    # 3. Format Response
    response = []
    for ent in entities:
        response.append({
            "id": ent.id,
            "name": ent.name,
            "full_name": ent.full_name,
            "type": ent.type,
            "file_path": ent.file.path, # Lazy load might trigger query, async accessible?
            # Warning: accessing relationship in async loop without selectinload might fail or be slow.
            # Ideally we should use selectinload(CodeEntity.file) in the query.
            # Let's fix query options.
            "start_line": ent.start_line,
            "end_line": ent.end_line
        })
        
    return response


@router.post("/projects/{project_id}/symbols/{symbol_id}/wiki")
async def generate_symbol_wiki(
    project_id: int,
    symbol_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate on-demand Wiki documentation for a specific symbol.
    """
    from app.domain.wiki.service import WikiService
    
    # Verify symbol belongs to project? (Optional security check)
    # For MVP just generate.
    
    wiki_service = WikiService(db)
    try:
        content = await wiki_service.generate_doc_for_entity(symbol_id)
        return {"content": content}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
