"""
Brain API Endpoints.
Exposes the Cognitive Kernel (Flash Brain) via REST.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.brain.drivers.llm_driver import ReflectiveDriver
from app.core.brain.drivers.ssm_driver import SSMDriver
from app.core.brain.filesystem.manager import BrainFileSystem
from app.core.brain.kernel import LightningKernel
from app.core.config import settings

router = APIRouter()

# Singleton Kernel Instance (Lazy Loading)
_kernel_instance: LightningKernel | None = None


async def get_kernel() -> LightningKernel:
    global _kernel_instance
    if _kernel_instance is None:
        fs = BrainFileSystem(settings.BRAIN_MEMORY_ROOT)
        ssm = SSMDriver()
        reflective = ReflectiveDriver()

        _kernel_instance = LightningKernel(ssm, fs, reflective)
        await _kernel_instance.initialize()

    return _kernel_instance


class BrainRequest(BaseModel):
    query: str
    max_depth: int = 3


class BrainResponse(BaseModel):
    response: str
    mode: str = "fast" # or "slow" if intercepted


@router.post("/chat", response_model=BrainResponse)
async def chat_with_brain(
    request: BrainRequest,
    current_user: CurrentUser
):
    """
    Direct interface to the 'Flash Brain'.
    By-passes the main Agent Graph, used for high-speed, low-cost reasoning.
    """
    kernel = await get_kernel()
    try:
        # Step through the cognitive loop
        response = await kernel.step(request.query, max_depth=request.max_depth)
        return BrainResponse(response=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
