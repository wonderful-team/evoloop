from fastapi import APIRouter

from .conversations import router as conversations_router
from .messages import router as messages_router
from .terminal import router as terminal_router

router = APIRouter()
router.include_router(conversations_router)
router.include_router(messages_router)
router.include_router(terminal_router)

__all__ = ["router"]
