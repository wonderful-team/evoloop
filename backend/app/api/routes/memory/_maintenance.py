import logging

from fastapi import APIRouter, Depends, HTTPException

from ._shared import get_memory_manager

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/maintenance/deduplicate-checkpoints")
async def deduplicate_checkpoints(
    dry_run: bool = True, manager=Depends(get_memory_manager)
):
    try:
        result = await manager.deduplicate_checkpoints(dry_run=dry_run)
        return result
    except Exception as e:
        logger.error(f"Failed to deduplicate checkpoints: {e}")
        raise HTTPException(status_code=500, detail=f"Deduplication failed: {str(e)}")
