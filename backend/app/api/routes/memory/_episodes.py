import logging

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUserOptional
from app.api.schemas.memory import EpisodeResponse

from ._shared import get_memory_manager

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/episodes/by-concept", response_model=list[EpisodeResponse])
async def get_episodes_by_concept(
    project_id: int,
    concept: str,
    limit: int = 10,
    manager=Depends(get_memory_manager),
    current_user: CurrentUserOptional = None,
):
    if not concept:
        return []
    try:
        results = await manager.find_episodes_by_concept(
            concept, project_id, limit, member_id=current_user.id if current_user else 0
        )
        return [
            EpisodeResponse(
                id=r["id"],
                goal=r["goal"],
                result=r["result"],
                error=None,
                timestamp=r["timestamp"],
            )
            for r in results
        ]
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.error(f"Failed to find episodes by concept: {e}")
        return []
