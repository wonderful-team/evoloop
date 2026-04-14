from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import TokenDep, require_benefit
from app.domain.wiki.schemas import WikiGenerationRequest, WikiGenerationResponse, WikiPageRead
from app.domain.wiki.service import wiki_service
from app.i18n.service import i18n

router = APIRouter(tags=["wiki"])


@router.get("/{project_id}", response_model=list[WikiPageRead])
async def get_wiki_pages(project_id: int, _token: TokenDep):
    """
    Get all wiki pages for a project.
    """
    return wiki_service.get_pages(project_id)


@router.post("/generate", dependencies=[Depends(require_benefit("wiki_generation"))])
async def generate_wiki(req: WikiGenerationRequest, _token: TokenDep) -> WikiGenerationResponse:
    """
    Trigger Wiki generation in background (Celery).
    """
    try:
        from app.domain.wiki.tasks import generate_wiki_task

        # Dispatch Celery Task
        task = generate_wiki_task.delay(
            project_id=req.project_id,
            topic=req.topic,
            force_regenerate=req.force_regenerate
        )

        return WikiGenerationResponse(
            status="accepted",
            message=i18n.get("wiki.generation_queued"),
            task_id=str(task.id),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
