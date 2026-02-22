"""
Flash Brain Node (SSM Integration).
Adapts the LightningKernel to the LangGraph Node interface.
"""
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.brain.drivers.ssm_driver import SSMDriver
from app.core.brain.filesystem.manager import BrainFileSystem
from app.core.brain.kernel import LightningKernel
from app.core.config import settings
from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)

# Singleton wrapper for the Brain Kernel in the graph context
_kernel_instance = None


async def get_or_create_kernel():
    global _kernel_instance
    if not _kernel_instance:
        logger.info("[FlashBrain] Initializing Kernel...")
        fs = BrainFileSystem(settings.BRAIN_MEMORY_ROOT)
        ssm = SSMDriver()
        await ssm.initialize()
        _kernel_instance = LightningKernel(ssm, fs)
        await _kernel_instance.initialize()
    return _kernel_instance


async def flash_brain_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Executes the Flash Brain (SSM) for fast reasoning tasks.
    registered as 'flash_brain' in the graph.
    """
    logger.info("[FlashBrain] Active")

    # 1. Get User Input / Context
    messages = state.get("messages", [])
    if not messages:
        return {"next_node": "supervisor"}

    execution_ticket = state.get("execution_ticket")
    topic = execution_ticket.get("topic") if execution_ticket else None

    # Fallback to last message content if no ticket topic
    if not topic:
        topic = messages[-1].content

    logger.info(f"[FlashBrain] Processing: {topic[:50]}...")

    # 2. Run Kernel
    try:
        kernel = await get_or_create_kernel()
        response_text = await kernel.step(topic)

        # 3. Format Response for Graph
        # We return an AIMessage so it looks like a normal agent response
        ai_msg = AIMessage(
            content=f"**[Flash Brain]**: {response_text}",
            name="flash_brain"
        )

        return {
            "messages": [ai_msg],
            "next_node": "supervisor", # Return control to Supervisor
            # Clear ticket
            "execution_ticket": None
        }
    except Exception as e:
        logger.error(f"[FlashBrain] Error: {e}")
        return {
            "messages": [AIMessage(content=f"Error in Flash Brain: {e}")],
            "next_node": "supervisor"
        }
