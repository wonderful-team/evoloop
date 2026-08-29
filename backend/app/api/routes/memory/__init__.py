from fastapi import APIRouter

from .concepts import router as concepts_router
from .episodes import router as episodes_router
from .maintenance import router as maintenance_router
from .search import router as search_router

router = APIRouter(tags=["memory"])
router.include_router(concepts_router)
router.include_router(search_router)
router.include_router(episodes_router)
router.include_router(maintenance_router)

__all__ = ["router"]
