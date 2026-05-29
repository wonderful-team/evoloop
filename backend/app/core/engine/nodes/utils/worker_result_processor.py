"""
Worker result post-processing pipeline.

Handles result summary, cache invalidation, verification capture,
MCP interception, and subtask result collection.
"""

import asyncio
import json
import logging

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.message.utils import get_message_text
from app.core.engine.routers import RoutingTarget
from app.core.engine.schemas import EngineResult
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.blackboard import SubtaskResult, VerificationStatus
from app.core.engine.state.config import ExecutionTicket
from app.core.engine.state.workspace import WorkspaceContext
from app.core.tools.registry import get_tool_metadata

logger = logging.getLogger(__name__)


async def process_worker_result(
    _node_name: str,
    state: AgentState,
    engine_result: EngineResult,
    execution_ticket: ExecutionTicket,
    role_name: str,
    config: RunnableConfig = None,
) -> StateUpdate:
    """
    Universal post-processing pipeline for Worker node execution.

    Handles: result summary, cache invalidation, verification capture, MCP interception,
    and subtask result collection.
    """
    # Guard against empty messages
    if not engine_result.messages:
        content = ""
    else:
        last_msg = engine_result.messages[-1]
        content = get_message_text(last_msg) if isinstance(last_msg, AIMessage) else ""

    tool_history = engine_result.tool_history or []
    routing_target = engine_result.routing_target

    # Single-shot subtasks may have empty AIMessage content after tool calls.
    # Fallback to the last ToolMessage content so aggregation has usable data.
    if not content and engine_result.messages:
        for msg in reversed(engine_result.messages):
            if isinstance(msg, ToolMessage):
                content = str(msg.content)
                break

    logger.info(f"[Worker][{role_name}] Loop finished. Content len: {len(content)}, Tools used: {len(tool_history)}, Target: {routing_target}")

    # Determine structured outcome using EngineResult.outcome if available
    outcome = engine_result.outcome
    if outcome and outcome.status == "truncated":
        # Preserve truncation signal so Supervisor can route back to Worker
        # without running LLM re-planning (which often hits max_tokens).
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

    # --- Structured outcome via Blackboard ---
    blackboard = state.blackboard
    agent_config = execution_ticket.agent_config if execution_ticket else None

    # Subtask workers do NOT set worker_outcome directly;
    # the Aggregator determines the final outcome after merging all parallel results.
    if not (agent_config and agent_config.is_subtask):
        blackboard.worker_outcome = worker_outcome

    # Update tool history in metadata
    blackboard.metadata.tool_history = (blackboard.metadata.tool_history or []) + tool_history

    # --- Subtask Result Collection ---
    if agent_config and agent_config.is_subtask:
        subtask_id = execution_ticket.subtask_id or "unknown"

        subtask_result = SubtaskResult(
            subtask_id=subtask_id,
            status="completed",
            result=content,
            tools_used=tool_history,
            timestamp=asyncio.get_event_loop().time(),
        )

        blackboard.subtask_results.append(subtask_result)

        pending_agg = blackboard.pending_aggregation
        if pending_agg:
            expected_count = pending_agg.expected_count or 0
            current_count = len(blackboard.subtask_results)
            logger.debug(f"[Worker] 📊 Subtask completion progress: {current_count}/{expected_count}")

            # Emit incremental heartbeat to main thread
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

    # 5a. Cache Invalidation (Universal via Metadata)
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

    # 5b. Verification Signal Capture
    verification_signals = []
    updated_execution_ticket = execution_ticket
    for t_sig in tool_history:
        tool_name = t_sig.split(":")[0] if ":" in t_sig else t_sig
        if tool_name not in verification_signals:
            verification_signals.append(tool_name)

        # 5c. MCP Server Interception
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

    blackboard.ticket = updated_execution_ticket
    blackboard.verification = verification_summary

    # 5d. Compile Technical Execution Trace (Handoff Report)
    trace_lines = []
    if tool_history:
        tool_counts = {}
        for t_sig in tool_history:
            t_name = t_sig.split(":")[0] if ":" in t_sig else t_sig
            tool_counts[t_name] = tool_counts.get(t_name, 0) + 1

        touched_files = set()
        if engine_result.messages:
            for msg in engine_result.messages:
                if getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        if tc.get("name") in ("edit_file", "write_file", "replace_file_content", "multi_replace_file_content", "write_to_file", "replace_content"):
                            args = tc.get("args", {})
                            path = args.get("path", "") or args.get("TargetFile", "")
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

    # Preserve ALL original messages (including ToolMessages) so that
    # retry/resume can reconstruct the full conversation history from
    # checkpoints.  The summarised content is injected as the *last*
    # AIMessage so the Supervisor still sees a concise worker output.
    preserved_messages = list(engine_result.messages or [])
    if preserved_messages and isinstance(preserved_messages[-1], AIMessage):
        # Overwrite the last AIMessage with the summarised content
        # Preserve additional_kwargs (including reasoning_content) from the original message
        original_msg = preserved_messages[-1]
        preserved_messages[-1] = AIMessage(
            content=worker_content,
            id=original_msg.id,
            additional_kwargs=original_msg.additional_kwargs,
            tool_calls=original_msg.tool_calls,
        )
    else:
        # Append a new summary AIMessage when there is no trailing AI msg
        preserved_messages.append(AIMessage(content=worker_content))

    return StateUpdate(
        messages=preserved_messages,
        next_node=routing_target or RoutingTarget.SUPERVISOR,
        blackboard=blackboard,
        workspace_context=workspace_context,
    )
