"""
HITL resume logic: build LangGraph Command to resume from a HITL interrupt.

Previously located in app.core.engine.background_agent.hitl.
"""

import logging
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.core.hitl.authorization import AuthorizationService
from app.core.hitl.orchestrator import HITLOrchestrator, get_pending_hitl_call

logger = logging.getLogger(__name__)


async def build_resume_command(
    graph_instance,
    config: dict,
    user_response: str,
) -> Any:
    """
    Build a LangGraph Command for resuming from HITL interrupt.

    For authorization-style HITL the pending approval stored in blackboard is
    converted into a persisted project-level grant when the user approves. The
    original blocked tool is then re-executed automatically so the user response
    does not appear as the tool result.
    """
    thread_id = config.get("configurable", {}).get("thread_id")

    # Detect pending tool call via standardized orchestrator
    pending_tool = await get_pending_hitl_call(graph_instance, config)

    if pending_tool:
        logger.info(f"Background Resume: Auto-completing tool {pending_tool['name']}")

        # Standardized normalization and DB state closure
        normalized_input = await HITLOrchestrator.handle_resume(
            thread_id=thread_id,
            tool_call=pending_tool,
            user_input=user_response,
        )

        # Authorization: persist the grant if user approved
        if normalized_input == "APPROVED":
            await _persist_authorization_grant(graph_instance, config, pending_tool)
            # Re-execute the original blocked tool so the LLM sees real tool output
            return await _build_authorized_retry_command(
                graph_instance=graph_instance,
                config=config,
                pending_tool=pending_tool,
            )

        # User rejected or cancelled: return a ToolMessage with the normalized signal
        tool_msg = ToolMessage(
            tool_call_id=pending_tool["id"],
            content=normalized_input,
        )
        return Command(resume=tool_msg)

    # Fallback or standard resume
    return Command(resume=user_response)


async def _persist_authorization_grant(graph_instance, config: dict, pending_tool: dict) -> None:
    """Convert a pending authorization HITL request into a persisted project grant."""
    try:
        thread_id = config.get("configurable", {}).get("thread_id")
        project_id = config.get("configurable", {}).get("project_id") or config.get("metadata", {}).get("project_id")
        tool_call_id = pending_tool.get("id")
        if not thread_id or not project_id or not tool_call_id:
            return

        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message

        resource_path = ""
        action = ""
        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(
                    Message.thread_id == thread_id,
                    Message.category == "hitl_request",
                    Message.tool_call_id == tool_call_id,
                )
                .order_by(Message.sequence_number.desc())
            )
            result = await session.execute(stmt)
            msg = result.scalars().first()
            if msg and msg.meta_data:
                auth_meta = msg.meta_data.get("authorization") or {}
                resource_path = auth_meta.get("resource_path", "")
                action = auth_meta.get("action", "")

        if not resource_path or not action:
            # Fallback to blackboard pending approvals if available
            current_state = await graph_instance.aget_state(config)
            if current_state.values:
                blackboard = current_state.values.get("blackboard")
                if blackboard and blackboard.metadata.pending_approvals:
                    for item in list(blackboard.metadata.pending_approvals):
                        if item.tool_call_id == tool_call_id:
                            resource_path = item.resource_path
                            action = item.action
                            break

        if resource_path and action:
            auth_service = AuthorizationService(project_id)
            ok = await auth_service.grant_permission(
                resource_path=resource_path,
                action=action,
            )
            logger.info(
                f"[Authorization] Persisted grant for {action} {resource_path}: {ok}"
            )
    except Exception as e:
        logger.warning(f"[Authorization] Failed to persist grant: {e}")


async def _build_authorized_retry_command(graph_instance, config: dict, pending_tool: dict) -> Any:
    """Re-run the tool that was blocked by the authorization gate.

    The approval has already been persisted as a project-level grant, so the
    authorization gate will let the same tool invocation pass on this retry.
    """
    try:
        from app.core.engine.state import AgentState
        from app.core.engine.tools.executor import AgentToolExecutor
        from app.core.tools.manager import tool_manager

        current_state = await graph_instance.aget_state(config)
        state = AgentState.model_validate(current_state.values)

        tools = await tool_manager.get_all_capabilities()
        tool_map = {t.name: t for t in tools if t.name}
        executor = AgentToolExecutor(
            tool_map=tool_map,
            state=state,
            config=config,
            name="AuthorizationRetry",
            enable_diff_tracking=False,
        )
        tool_name = pending_tool["name"]
        tool_args = pending_tool.get("args", {})
        tool_id = pending_tool["id"]
        result = await executor.execute_tool(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_id=tool_id,
            local_tool_history=[],
        )
        return Command(resume=result.message)
    except Exception as e:
        logger.warning(f"[Authorization] Failed to re-execute approved tool: {e}")
        # Fall back to a rejection signal so the agent does not receive a fake success
        tool_msg = ToolMessage(
            tool_call_id=pending_tool["id"],
            content="REJECTED",
        )
        return Command(resume=tool_msg)
