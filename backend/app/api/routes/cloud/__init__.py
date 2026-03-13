"""
Cloud API Routes - Exposed to EvoLoop Client devices.

These endpoints allow client devices to:
- Access centralized Agent intelligence
- Query Long-Term Memory (LTM)
- Download synthesized Skills
- Sync Atlas knowledge
"""

from fastapi import APIRouter

from .agent import router as agent_router
from .memory import router as memory_router
from .skill import router as skill_router
from .device import router as device_router

router = APIRouter(prefix="/cloud", tags=["cloud"])

router.include_router(agent_router, prefix="/agent")
router.include_router(memory_router, prefix="/memory")
router.include_router(skill_router, prefix="/skill")
router.include_router(device_router, prefix="/device")

__all__ = ["router"]
