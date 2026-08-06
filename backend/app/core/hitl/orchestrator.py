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
                    authorization = last_hitl.meta_data.get("authorization") or {}
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
                            # authorization 元数据（resource_path/action）标记这是
                            # 授权门控工具，审批后应重执行而非仅回显 APPROVED。
                            "authorization": authorization if authorization else None,
                        }
    except Exception as e:
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
    except Exception as e:
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
            except Exception as e:
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
            except Exception as e:
                logger.warning(f"[HITL] cancel_request failed for {request_id}: {e}")
        return "CANCELLED"

    @staticmethod
    async def resolve_approved_tool_result(
        pending_tool: dict,
        config: dict,
        fallback_result: str,
        state=None,
    ) -> str:
        """审批后的工具结果：授权门控工具记录授权并重执行，返回真实结果；否则回退。

        对 confirmation 类工具，``APPROVED`` 就是答案（``fallback_result``）。
        对 authorization 门控工具（``pending_tool["authorization"]`` 存在），
        审批后必须用原始参数重执行工具——否则工具会被标记完成但从未执行
        （副作用缺失，Agent 却报告成功）。
        """
        authorization = pending_tool.get("authorization")
        if not authorization:
            return fallback_result

        project_id = config.get("metadata", {}).get("project_id") or 0
        from app.core.hitl.authorization import AuthorizationService

        try:
            await AuthorizationService(project_id).grant_permission(
                resource_path=authorization.get("resource_path", ""),
                action=authorization.get("action", "read"),
                granted_by="hitl-approval",
            )
        except Exception as e:
            logger.warning(f"[HITL] grant_permission failed for approval: {e}")

        if state is None:
            from app.core.engine.state import AgentState

            state = AgentState(
                thread_id=config.get("configurable", {}).get("thread_id"),
                project_id=project_id,
            )

        tool_name = pending_tool.get("name")
        tool_args = pending_tool.get("args") or {}
        tool_call_id = pending_tool.get("id")
        try:
            from app.core.engine.tools.executor import AgentToolExecutor
            from app.core.tools.manager import tool_manager

            tool_map = {
                t.name: t for t in await tool_manager.get_node_tools("worker", state)
            }
            executor = AgentToolExecutor(
                tool_map=tool_map, state=state, config=config, name="HITLResume"
            )
            result = await executor.execute_tool(tool_name, tool_args, tool_call_id, [])
            return result.message.content or ""
        except Exception as e:
            logger.error(f"[HITL] Re-execution failed for {tool_name}: {e}")
            return f"[HITL Re-execution Failed] {e}"

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
