"""
Learning API Routes — package with sub-routers.

Routes are split by functional domain:
- hitl: human-in-the-loop requests
- skills: skill CRUD, validation, YAML import/export
- recording: trace recording sessions
- synthesis: multimodal skill synthesis from recordings
- mirror: device mirroring, event capture, extract points
- capabilities: action registry
"""

from fastapi import APIRouter

from .capabilities import router as capabilities_router
from .hitl import router as hitl_router
from .mirror import router as mirror_router
from .recording import router as recording_router
from .skills import router as skills_router
from .synthesis import router as synthesis_router

router = APIRouter()

router.include_router(capabilities_router)
router.include_router(hitl_router)
router.include_router(skills_router)
router.include_router(recording_router)
router.include_router(synthesis_router)
router.include_router(mirror_router)

__all__ = ["router"]
