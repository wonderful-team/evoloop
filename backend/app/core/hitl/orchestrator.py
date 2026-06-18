"""
HITL orchestrator: detection, normalization, state closure, and authorization.

Previously located in app.core.engine.hitl.
"""

import logging

from app.core.engine.message.repository import MessageRepository
from app.core.hitl.core import (
    HumanInputRequest,
    create_request,
    push_hitl_notification,
    raise_hitl_interrupt,
)
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

    # --- FALLBACK: Authorization-style HITL persisted in Message table ---
    try:
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            from sqlalchemy import select

            from app.infrastructure.database.sql.database import session_scope
            from app.models import Message

            async with session_scope() as session:
                stmt = (
                    select(Message)
                    .where(
                        Message.thread_id == thread_id,
                        Message.role == "system",
                        Message.category == "hitl_request",
                        Message.status == "waiting_human",
                    )
                    .order_by(Message.sequence_number.desc())
                )
                res = await session.execute(stmt)
                last_hitl = res.scalars().first()

                if last_hitl and last_hitl.meta_data:
                    original = last_hitl.meta_data.get("original_tool") or {}
                    t_name = original.get("name") or last_hitl.tool_name
                    t_call_id = last_hitl.tool_call_id or last_hitl.id
                    t_args = original.get("args") or {}
                    if t_name and t_call_id:
                        logger.info(
                            f"[HITL] Located pending authorization request for "
                            f"{t_name} ({t_call_id}) from Message table fallback."
                        )
                        return {
                            "id": t_call_id,
                            "name": t_name,
                            "args": t_args,
                        }
    except Exception as e:
        logger.warning(f"Failed message fallback for pending HITL call: {e}")

    return None


def normalize_hitl_input(_tool_name: str, user_input: str | None) -> str:
    """
    Normalizes raw user input into a format expected by specialized HITL tools.
    e.g., converts "yes" -> "APPROVED" for confirmation tools.
    """
    if not user_input:
        return "APPROVED"  # Default fallback for empty approval

    lower_input = user_input.lower().strip()

    # Universal approval/rejection normalization (covers authorization-style HITL
    # where the original blocked tool name is not a standard HITL tool).
    if lower_input in ("yes", "approve", "approved", "confirm", "ok", "y"):
        return "APPROVED"
    if lower_input in ("no", "reject", "rejected", "cancel", "deny", "n"):
        return "REJECTED"

    return user_input


async def close_hitl_interaction(
    thread_id: str, tool_call_id: str, status: str = "completed"
) -> None:
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
    Handles detection, normalization, state closure, and authorization.
    """

    @staticmethod
    async def get_pending_request(graph, thread_id: str, model: str) -> dict | None:
        """Standardized detection of pending HITL calls."""
        config = {"configurable": {"thread_id": thread_id, "model": model}}
        return await get_pending_hitl_call(graph, config)

    @staticmethod
    async def handle_resume(
        thread_id: str, tool_call: dict, user_input: str | None
    ) -> str:
        """Processes resume logic: normalization and DB closure."""
        normalized = normalize_hitl_input(tool_call["name"], user_input)
        await close_hitl_interaction(thread_id, tool_call["id"], "completed")
        return normalized

    @staticmethod
    async def handle_cancel(thread_id: str, tool_call: dict) -> None:
        """Processes cancellation logic: DB closure."""
        await close_hitl_interaction(thread_id, tool_call["id"], "cancelled")

    @staticmethod
    async def request_authorization(
        thread_id: str,
        action_description: str,
        resource_path: str,
        risk_level: str,
        policy: dict,
        project_id: int | None = None,
        run_id: str | None = None,
        tool_call_id: str | None = None,
        parent_id: str | None = None,
        original_tool_name: str | None = None,
        original_tool_args: dict | None = None,
    ) -> HumanInputRequest:
        """
        Trigger an authorization-style HITL request.

        This method is intended to be called from the authorization gate hook, not
        from an explicit tool. It reuses the `approval` request type so the existing
        frontend UI (Approve/Reject) works without changes.
        """
        from app.i18n.service import i18n

        risk_emoji = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "critical": "🔴",
        }
        localized_risk = i18n.get(
            f"common.risk_levels.{risk_level}", default=risk_level.upper()
        )

        context = f"""{risk_emoji.get(risk_level, '⚪')} {i18n.get("common.risk_levels.label", level=localized_risk)}

{i18n.get("domain_tools.human_input.authorization.resource", path=resource_path)}
{i18n.get("domain_tools.human_input.authorization.action", action=action_description)}

{policy.get("description", "")}"""

        request = await create_request(
            thread_id=thread_id,
            request_type="approval",
            prompt=action_description,
            context=context,
            default_value="REJECTED",
        )

        response_text = i18n.get(
            "domain_tools.human_input.approval_template",
            id=request.id,
            approval_context=context,
        )

        await push_hitl_notification(
            thread_id=thread_id,
            request=request,
            request_data={
                "type": "approval",
                "prompt": action_description,
                "context": context,
                "default_value": "REJECTED",
                "risk_level": risk_level,
                "resource_path": resource_path,
            },
            project_id=project_id,
            run_id=run_id,
            tool_name="request_approval",
            tool_call_id=tool_call_id,
            parent_id=parent_id,
            original_tool_name=original_tool_name,
            original_tool_args=original_tool_args,
            resource_path=resource_path,
            action=action_description.split(" ", 1)[0] if action_description else "",
        )

        raise_hitl_interrupt(request.id, response_text)
        return request  # unreachable
