"""
Worker result post-processing pipeline.

Handles result summary, cache invalidation, verification capture,
MCP interception, and subtask result collection.
"""

import json
import logging

from app.core.engine.message.native_classes import (
    AIMessage,
    RunnableConfig,
)
from app.core.engine.message.utils import get_message_text
from app.core.engine.schemas import EngineResult
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.config import ExecutionTicket
from app.core.engine.state.sub_schemas import SubtaskResult, VerificationStatus
from app.core.engine.state.workspace import WorkspaceContext
from app.core.tools.registry import get_tool_metadata

logger = logging.getLogger(__name__)


async def process_worker_result(
    node_name: str,
    state: AgentState,
    engine_result: EngineResult,
    execution_ticket: ExecutionTicket,
    role_name: str,
    config: RunnableConfig = None,
) -> StateUpdate:
    if not engine_result.messages:
        content = ""
    else:
        last_msg = engine_result.messages[-1]
        last_role = last_msg.role
        content = get_message_text(last_msg) if last_role in ("assistant", "ai") else ""

    tool_history = engine_result.tool_history or []

    if not content and engine_result.messages:
        for msg in reversed(engine_result.messages):
            if msg.role == "tool":
                content = get_message_text(msg)
                break

    logger.info(f"[Worker][{role_name}] Loop finished. Content len: {len(content)}, Tools used: {len(tool_history)}")

    outcome = engine_result.outcome
    if outcome and outcome.status == "truncated":
        worker_outcome = "truncated"
        if execution_ticket:
            execution_ticket.is_resuming = True
    elif outcome and outcome.status in ("failed", "error"):
        worker_outcome = "failed"
        if execution_ticket:
            execution_ticket.is_resuming = False
    elif "[ERROR:" in content or content.strip().startswith("Error:"):
        worker_outcome = "failed"
        if execution_ticket:
            execution_ticket.is_resuming = False
    else:
        worker_outcome = "success"
        if execution_ticket:
            execution_ticket.is_resuming = False

    parameters = execution_ticket.parameters
    verbose_output = parameters.verbose_output if parameters else True

    if verbose_output:
        worker_content = content if content else f"{role_name} completed."
    else:
        worker_content = f"{role_name} completed."

    agent_config = execution_ticket.agent_config if execution_ticket else None

    out_outcome = None
    if not (agent_config and agent_config.is_subtask):
        out_outcome = worker_outcome

    out_subtask_results = []
    if agent_config and agent_config.is_subtask:
        subtask_id = execution_ticket.subtask_id or "unknown"

        subtask_result = SubtaskResult(
            subtask_id=subtask_id,
            status="completed",
            result=content,
            tools_used=tool_history,
            timestamp=asyncio.get_running_loop().time(),
        )

        out_subtask_results = [subtask_result]

        pending_agg = state.pending_aggregation
        if pending_agg:
            expected_count = pending_agg.expected_count or 0
            current_count = len(state.subtask_results) + 1
            logger.debug(f"[Worker] 📊 Subtask completion progress: {current_count}/{expected_count}")

            if config:
                from app.core.monitoring.activity import activity_monitor
                main_thread_id = execution_ticket.parent_task_id or "unknown"
                if main_thread_id != "unknown":
                    await activity_monitor.update_agent_state(
                        thread_id=main_thread_id,
                        mode="EXECUTING",
                        task_name=f"Parallel Execution ({current_count}/{expected_count})",
                        task_status=f"Subtask '{subtask_id}' completed."
                    )

    has_changes = False
    for t_sig in tool_history:
        tool_name = t_sig.split(":")[0] if ":" in t_sig else t_sig
        meta = get_tool_metadata(tool_name)
        if meta and meta.get("is_state_mutating"):
            has_changes = True
            logger.info(f"[Worker][{role_name}] ♻️ State mutation detected via tool '{tool_name}' - Invalidating caches")
            break

    workspace_context = None
    if has_changes:
        workspace_context = WorkspaceContext(structure=None, structure_updated_at=0.0)

    verification_signals = []
    updated_execution_ticket = execution_ticket
    for t_sig in tool_history:
        tool_name = t_sig.split(":")[0] if ":" in t_sig else t_sig
        if tool_name not in verification_signals:
            verification_signals.append(tool_name)

        if tool_name == "use_mcp_server":
            try:
                args_json = t_sig.split(":", 1)[1]
                args = json.loads(args_json)
                server_name = args.get("server_name")
                if server_name:
                    req_servers = set(updated_execution_ticket.mcp_servers_required or [])
                    req_servers.add(server_name)
                    updated_execution_ticket.mcp_servers_required = list(req_servers)
                    logger.info(f"[Worker] 🔌 Appended MCP server '{server_name}' to execution_ticket.")
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                logger.error(f"[Worker] Failed to parse use_mcp_server arguments: {e}")

    verification_summary = VerificationStatus(status="unverified", signals=verification_signals)

    trace_lines = []
    if tool_history:
        tool_counts = {}
        for t_sig in tool_history:
            t_name = t_sig.split(":")[0] if ":" in t_sig else t_sig
            tool_counts[t_name] = tool_counts.get(t_name, 0) + 1

        touched_files = set()
        if engine_result.messages:
            for msg in engine_result.messages:
                if msg.role not in ("assistant", "ai"):
                    continue
                msg_tcs = msg.tool_calls
                if msg_tcs:
                    for tc in msg_tcs:
                        tc_name = tc.get("name")
                        if tc_name in ("edit_file", "write_file", "replace_file_content", "multi_replace_file_content", "write_to_file", "replace_content"):
                            tc_args = tc.get("args", {})
                            path = tc_args.get("path", "") or tc_args.get("TargetFile", "")
                            if path:
                                touched_files.add(path)

        trace_lines.append("\n\n--- 🛠️ Technical Execution Trace ---")
        trace_lines.append(f"Tools executed ({len(tool_history)} total): " + ", ".join([f"{k} ({v})" for k, v in tool_counts.items()]))
        if touched_files:
            trace_lines.append(f"Files modified: {', '.join(list(touched_files)[:5])}")
            if len(touched_files) > 5:
                trace_lines[-1] += f" (+{len(touched_files)-5} more)"

        if worker_outcome == "truncated":
            trace_lines.append("⚠️ Execution was forcefully TRUNCATED due to max_steps timeout.")
        elif worker_outcome == "failed":
            trace_lines.append("❌ Execution FAILED. Check recent tool errors.")

    technical_trace = "\n".join(trace_lines) if trace_lines else ""
    worker_content = worker_content + technical_trace

    preserved_messages = list(engine_result.messages or [])
    if preserved_messages:
        last_pm = preserved_messages[-1]
        last_pm_role = last_pm.role
        if last_pm_role in ("assistant", "ai"):
            preserved_messages[-1] = AIMessage(
                content=worker_content,
                id=last_pm.id,
                additional_kwargs=last_pm.additional_kwargs,
                tool_calls=last_pm.tool_calls,
            )
        else:
            preserved_messages.append(AIMessage(content=worker_content))
    else:
        preserved_messages.append(AIMessage(content=worker_content))

    return StateUpdate(
        messages=preserved_messages,
        next_node=None,
        workspace_context=workspace_context,
        worker_outcome=out_outcome,
        subtask_results=out_subtask_results,
        ticket=updated_execution_ticket,
        verification=verification_summary,
        tool_history=tool_history,
    )
