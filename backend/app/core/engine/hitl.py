import logging

from app.core.engine.message.repository import MessageRepository
from app.core.tools.registry import is_hitl_tool

logger = logging.getLogger(__name__)

async def get_pending_hitl_call(graph, config: dict) -> dict | None:
    """
    Detects if the graph is currently interrupted by a HITL-enabled tool.
    Returns the tool_call dictionary if found, otherwise None.
    """
    try:
        current_state = await graph.aget_state(config)
        if current_state.values and "messages" in current_state.values:
            history = current_state.values["messages"]
            if history:
                last_msg = history[-1]
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    last_tool_call = last_msg.tool_calls[-1]
                    if is_hitl_tool(last_tool_call["name"]):
                        return last_tool_call
    except Exception as e:
        logger.warning(f"Failed to detect pending HITL call: {e}")
        
    # --- FALLBACK: Query Database for pending/running HITL tool call ---
    try:
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            from app.infrastructure.database.sql.database import session_scope
            from app.models import Message
            from sqlalchemy import select
            
            async with session_scope() as session:
                # Find the latest running tool message
                stmt = select(Message).where(
                    Message.thread_id == thread_id,
                    Message.role == "tool",
                    Message.status == "running"
                ).order_by(Message.sequence_number.desc())
                res = await session.execute(stmt)
                last_running = res.scalars().first()
                
                if last_running and last_running.meta_data:
                    t_name = last_running.meta_data.get("tool_name")
                    t_call_id = last_running.meta_data.get("tool_call_id")
                    if t_name and t_call_id and is_hitl_tool(t_name):
                        logger.info(f"[HITL] Located pending tool call {t_name} from database fallback.")
                        return {
                            "id": t_call_id,
                            "name": t_name,
                            "args": last_running.meta_data.get("input") or {}
                        }
    except Exception as e:
        logger.warning(f"Failed database fallback for pending HITL call: {e}")
        
    return None

def normalize_hitl_input(tool_name: str, user_input: str | None) -> str:
    """
    Normalizes raw user input into a format expected by specialized HITL tools.
    e.g., converts "yes" -> "APPROVED" for confirmation tools.
    """
    if not user_input:
        return "APPROVED"  # Default fallback for empty approval
        
    # Standard mapping for confirmation tools
    if tool_name in ("ask_confirm", "request_approval"):
        lower_input = user_input.lower().strip()
        if lower_input in ("yes", "approve", "confirm", "ok", "y"):
            return "APPROVED"
        if lower_input in ("no", "reject", "cancel", "deny", "n"):
            return "REJECTED"
            
    return user_input

async def close_hitl_interaction(thread_id: str, tool_call_id: str, status: str = "completed"):
    """
    Atomically updates the status of the HITL request message in the database.
    """
    try:
        repo = MessageRepository(thread_id=thread_id)
        success = await repo.update_status_by_tool_call_id(tool_call_id, status)
        if success:
            logger.debug(f"HITL interaction {tool_call_id} closed as {status}")
        else:
            logger.warning(f"Failed to find HITL message for tool_call_id: {tool_call_id}")
    except Exception as e:
        logger.error(f"Error closing HITL interaction: {e}")


class HITLOrchestrator:
    """
    Unified orchestrator for Human-In-The-Loop interactions.
    Handles detection, normalization, and state closure.
    """

    @staticmethod
    async def get_pending_request(graph, thread_id: str, model: str) -> dict | None:
        """Standardized detection of pending HITL calls."""
        config = {"configurable": {"thread_id": thread_id, "model": model}}
        return await get_pending_hitl_call(graph, config)

    @staticmethod
    async def handle_resume(thread_id: str, tool_call: dict, user_input: str | None) -> str:
        """Processes resume logic: normalization and DB closure."""
        normalized = normalize_hitl_input(tool_call["name"], user_input)
        await close_hitl_interaction(thread_id, tool_call["id"], "completed")
        return normalized

    @staticmethod
    async def handle_cancel(thread_id: str, tool_call: dict):
        """Processes cancellation logic: DB closure."""
        await close_hitl_interaction(thread_id, tool_call["id"], "cancelled")
