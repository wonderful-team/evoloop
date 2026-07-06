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

logger = logging.getLogger(__name__)


async def get_pending_hitl_call(config: dict) -> dict | None:
    """
    Detects a pending HITL request from the Message table.
    Returns the tool_call dictionary if found, otherwise None.
    """
    try:
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            from sqlalchemy import select

            from app.infrastructure.database import session_scope
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
                    request_id = last_hitl.meta_data.get("hitl_request_id")
                    if t_name and t_call_id:
                        logger.info(
                            f"[HITL] Located pending authorization request for "
                            f"{t_name} ({t_call_id}) from Message table."
                        )
                        return {
                            "id": t_call_id,
                            "name": t_name,
                            "args": t_args,
                            "request_id": request_id,
                        }
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to find pending HITL call: {e}")

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
    if lower_input in ("no", "reject", "rejected", "cancel", "cancelled", "deny", "n"):
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
            logger.warning(
                f"Failed to find HITL message for tool_call_id: {tool_call_id}"
            )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Error closing HITL interaction: {e}")


class HITLOrchestrator:
    """
    Unified orchestrator for Human-In-The-Loop interactions.
    Handles detection, normalization, state closure, and authorization.
    """

    @staticmethod
    async def get_pending_request(thread_id: str, model: str) -> dict | None:
        """Standardized detection of pending HITL calls from the Message table."""
        config = {"configurable": {"thread_id": thread_id, "model": model}}
        return await get_pending_hitl_call(config)

    @staticmethod
    async def handle_resume(
        thread_id: str, tool_call: dict, user_input: str | None
    ) -> str:
        """Processes resume logic: normalization, DB closure, activity cleanup, and human_requests closure."""
        from app.core.hitl.core import complete_request
        from app.core.monitoring.activity import activity_monitor

        normalized = normalize_hitl_input(tool_call["name"], user_input)
        await close_hitl_interaction(thread_id, tool_call["id"], "completed")
        await activity_monitor.clear_human_request(thread_id)
        request_id = tool_call.get("request_id")
        if request_id:
            try:
                await complete_request(request_id, normalized)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"[HITL] complete_request failed for {request_id}: {e}")
        return normalized

    @staticmethod
    async def handle_cancel(thread_id: str, tool_call: dict) -> str:
        """Processes cancellation logic: DB closure, activity cleanup, and human_requests closure."""
        from app.core.hitl.core import cancel_request
        from app.core.monitoring.activity import activity_monitor

        await close_hitl_interaction(thread_id, tool_call["id"], "cancelled")
        await activity_monitor.clear_human_request(thread_id)
        request_id = tool_call.get("request_id")
        if request_id:
            try:
                await cancel_request(request_id)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"[HITL] cancel_request failed for {request_id}: {e}")
        return "CANCELLED"

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

        context = f"""{risk_emoji.get(risk_level, "⚪")} {i18n.get("common.risk_levels.label", level=localized_risk)}

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
