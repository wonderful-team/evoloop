import asyncio
import json
import re
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from sqlalchemy import desc, select

from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models import Message
from app.core.evocloud import evocloud_manager
from app.models.schemas.events import MessageEvent


class DatabaseCallbackHandler(AsyncCallbackHandler):
    """
    Callback Handler that logs user-friendly messages to the database.
    Acts as a View Layer sanitizer.
    """

    def __init__(self, thread_id: str, project_id: int, start_sequence: int = 0, run_id: str = None):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id  # Phase 3: Associate messages with runs
        self._sequence_counter = start_sequence  # Track message order within thread
        self._run_tool_map = {}  # Map run_id to tool_name for visibility filtering

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        pass

    async def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any) -> Any:
        """Track which tool is running for a given run_id."""
        tool_name = serialized.get("name")
        if tool_name:
            self._run_tool_map[str(run_id)] = tool_name

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        pass

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        try:
            if not response.generations:
                return

            generation = response.generations[0][0]
            message = generation.message  # type: ignore
            content = message.content or ""

            # Handle Multimodal/List content (e.g. Anthropic/Zhipu structured output)
            if isinstance(content, list):
                # Extract text elements
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_use":
                            pass
                    elif isinstance(item, str):
                        text_parts.append(item)
                content = "".join(text_parts)

            # Defensive: Ensure content is string
            if not isinstance(content, str):
                content = str(content)

            # 1. Parse Thinking
            thinking = None
            think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
            if think_match:
                thinking = think_match.group(1).strip()
                content = content.replace(think_match.group(0), "").strip()

            # 2. Detect and Format JSON (Supervisor/Router Outputs)
            if content and content.strip().startswith("{") and content.strip().endswith("}"):
                try:
                    data = json.loads(content)
                    # Case A: Routing Decision
                    if "next_node" in data:
                        node = data.get("next_node")
                        parallel = data.get("parallel_research_tasks")
                        if node == "finish":
                            # INTERCEPT: Update Cloud Status instead of logging message
                            # thread_id format: task-{task_id}-{timestamp}
                            task_match = re.search(r"task-(\d+)-", self.thread_id)
                            if task_match:
                                task_id = int(task_match.group(1))
                                if evocloud_manager.api:
                                    asyncio.create_task(evocloud_manager.api.update_task_status(task_id, 3, 100))

                            return  # Do not log 'finish' JSON to chat

                        # Case B: Other JSON
                        # Convert to nicely formatted text
                        content = i18n.get("prompts.database_logger.decision", node=node)
                        if parallel:
                            content += i18n.get("prompts.database_logger.analysis", analysis=parallel)
                except Exception:
                    pass

            # Persist to DB
            tool_calls = getattr(message, "tool_calls", None)
            await self._save_log(
                role="assistant",
                content=content,
                thinking=thinking,
                tool_calls=tool_calls,
            )

        except Exception:
            # Swallow errors in logging to prevent crashing the flow
            pass

    def _get_tool_summary(self, tool_call: dict) -> str:
        """Generate a user-friendly summary of what a tool is doing."""
        tool_name = tool_call.get("name", "tool")
        tool_input = tool_call.get("args", {})

        # Phase 18: Support new atomic file tools
        if tool_name == "read_file":
            path = tool_input.get("path", "file")
            return i18n.get("prompts.database_logger.tool_summary.read_file", path=path)
        elif tool_name == "write_file":
            path = tool_input.get("path", "file")
            return i18n.get("prompts.database_logger.tool_summary.write_file", path=path)
        elif tool_name == "edit_file":
            path = tool_input.get("path", "file")
            return i18n.get("prompts.database_logger.tool_summary.edit_file", path=path)
        elif tool_name == "list_files":
            path = tool_input.get("path", "directory")
            return i18n.get("prompts.database_logger.tool_summary.list_files", path=path)
        elif tool_name == "file_system":
            action = tool_input.get("action", "operate")
            path = tool_input.get("path", "path")
            return i18n.get("prompts.database_logger.tool_summary.operate_file", action=action.capitalize(), path=path)
        elif tool_name == "manage_file":
            action = tool_input.get("action", "access")
            path = tool_input.get("path", "file")
            return i18n.get(
                "prompts.database_logger.tool_summary.manage_file",
                action=action.replace("_", " ").capitalize(),
                path=path,
            )
        elif tool_name == "search_codebase":
            query = tool_input.get("query", "")
            return i18n.get("prompts.database_logger.tool_summary.search_code", query=query)
        elif tool_name == "request_human_input":
            return i18n.get("prompts.database_logger.tool_summary.ask_user", prompt=tool_input.get("prompt", ""))

        return i18n.get("prompts.database_logger.tool_summary.default", tool=tool_name)

    def _extract_reference(self, tool_call: dict) -> dict | None:
        """Extract structure reference data from tool call"""
        t_name = tool_call.get("name", "tool")
        t_args = tool_call.get("args", {})

        try:
            # Phase 18: Support new atomic file tools
            if t_name in [
                "read_document",
                "read_file",
                "view_file",
                "manage_file",
                "list_files",
                "write_file",
                "edit_file",
            ]:
                path = (
                    t_args.get("file_path")
                    or t_args.get("AbsolutePath")
                    or t_args.get("url")
                    or t_args.get("path")
                    or "unknown"
                )
                name = path.split("/")[-1]
                return {"type": "file", "target_id": path, "target_name": name}

            elif t_name in ["search_codebase", "grep_search", "find_by_name"]:
                query = t_args.get("query") or t_args.get("Pattern") or "unknown"
                return {
                    "type": "knowledge",
                    "target_id": query,
                    "target_name": i18n.get("prompts.database_logger.ref_search", query=query),
                }

            elif t_name == "read_memory_item":  # Hypothetical tool for memory
                mem_id = t_args.get("id", "unknown")
                return {
                    "type": "memory",
                    "target_id": mem_id,
                    "target_name": i18n.get("prompts.database_logger.ref_memory"),
                }

            return None
        except Exception:
            return None

    # Implement on_tool_end to capture tool outputs
    async def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        # Capture tool output
        # Used for history and debugging

        # 1. Determine Tool Name and Visibility
        run_id_str = str(run_id)
        tool_name = self._run_tool_map.get(run_id_str, "unknown_tool")

        # Clean up map
        if run_id_str in self._run_tool_map:
            del self._run_tool_map[run_id_str]

        visibility = self._get_tool_visibility(tool_name)
        if visibility == "HIDDEN":
            return

        # 2. Process Content (Folding/Summarizing)
        # Phase 17: Deprecate Folding. Store strict raw output in content with action_type='tool_output'.
        # Frontend handles display logic (Accordion).
        
        await self._save_log(
            role="tool",
            content=str(output),
            status="completed",
            action_type="tool_output",
        )

    def _get_tool_visibility(self, tool_name: str) -> str:
        # ... (Keep existing visibility logic if needed for HIDDEN check)
        # But FOLDED logic is now handled by frontend via action_type
        return "VISIBLE" 

    # _summarize_tool_output is now unused but can be kept for reference or deleted.

    async def _save_log(
        self,
        role: str,
        content: str,
        thinking: str | None = None,
        status: str = "completed",
        references: list[dict] | None = None,
        tool_calls: list | None = None,
        tool_output: str | None = None, # Deprecated
        action_type: str = "text",
    ):
        # Phase 18 Fix: Sanitize content for PostgreSQL (No NUL bytes)
        if content:
            # 1. Strip NUL bytes which crash Postgres TEXT fields
            content = content.replace("\x00", "")
            
            # 2. Truncate excessively large outputs (e.g. 300KB+ binary dumps)
            # to keep DB and frontend performance stable.
            LIMIT = 100000
            if len(content) > LIMIT:
                content = content[:LIMIT] + f"\n\n... (Truncated {len(content) - LIMIT} characters) ..."

        if not content and not thinking and not tool_calls:
            return

        # ... (Dedup logic unchanged)
        current_time = time.time()
        current_hash = hash((role, content, str(tool_calls))) if content else 0

        last_hash = getattr(self, "_last_logged_hash", None)
        last_time = getattr(self, "_last_logged_time", 0)

        if current_hash == last_hash and (current_time - last_time) < 2.0:
            return

        self._last_logged_hash = current_hash
        self._last_logged_time = current_time

        try:
            self._sequence_counter += 1
            async with session_scope() as session:
                # ... (Parent ID logic unchanged)
                parent_id = None
                stmt = (
                    select(Message.id)
                    .where(Message.thread_id == self.thread_id)
                    .order_by(desc(Message.sequence_number))
                    .limit(1)
                )
                result = await session.execute(stmt)
                parent_id = result.scalar_one_or_none()

                log = Message(
                    thread_id=self.thread_id,
                    project_id=self.project_id,
                    role=role,
                    content=content,
                    thinking=thinking,
                    sequence_number=self._sequence_counter,
                    run_id=self.run_id,
                    status=status,
                    parent_id=parent_id,
                    tool_calls=tool_calls,
                    # tool_output=tool_output, # DEPRECATED
                    action_type=action_type,
                )
                session.add(log)
                await session.flush()  # Get ID

                # Phase 11: Real-time History Sync
                try:
                    from app.core.monitoring.activity import activity_monitor

                    # Map action_type to frontend type
                    # Mobile expects: 'user', 'thought', 'tool', 'error', 'hitl_request'
                    frontend_type = "text"
                    if log.role == "user":
                        frontend_type = "user"
                    elif log.action_type == "tool_output":
                        frontend_type = "tool"
                    elif log.action_type == "thinking":
                        frontend_type = "thought"
                    
                    msg_data = {
                        "id": str(log.id),
                        "role": log.role,
                        "content": log.content,
                        "thinking": log.thinking,
                        "type": frontend_type, 
                        "action_type": log.action_type,
                        "tool_calls": log.tool_calls,
                    }

                    # Fire and forget
                    if activity_monitor and hasattr(activity_monitor, "client"):
                        await activity_monitor.client.publish(
                            f"chat:{self.thread_id}:events",
                            MessageEvent(data=msg_data).json(),
                        )
                except Exception:
                    pass

                # Phase 9: Save References
                if references:
                    from app.models import MessageReference

                    for ref in references:
                        mr = MessageReference(
                            id=str(UUID(int=hash(f"{log.id}-{ref['target_id']}-{time.time()}") & ((1 << 128) - 1))),
                            # Pseudo UUID
                            message_id=log.id,
                            type=ref["type"],
                            target_id=ref["target_id"],
                            target_name=ref["target_name"],
                        )
                        session.add(mr)

                # session_scope commits automatically
        except Exception as e:
            # Phase 18 Fix: Log error explicitly. Do not swallow fatal DB errors silently,
            # although we might still want to avoid crashing the whole agent if just logging fails?
            # Actually, if logging fails, we lose history. It's critical.
            # But crashing the agent mid-thought is also bad.
            # Let's log ERROR and re-raise if it's a connection issue?
            # For now, just logging ERROR is better than silent 'pass'.
            import logging
            logging.getLogger(__name__).error(f"CRITICAL: Failed to persist message log: {e}", exc_info=True)
            # We don't re-raise to avoid killing the agent execution loop,
            # but this error will now be visible in logs.

    async def snapshot_steps_to_last_message(self, steps: list):
        """
        Phase 6: Persist executed steps to the last AI message for historical rendering.
        Called when a run completes (done/failed/cancelled).
        """
        if not steps:
            return

        try:
            async with session_scope() as session:
                # Find the last AI message for this thread/run
                stmt = (
                    select(Message)
                    .where(Message.thread_id == self.thread_id)
                    .where(Message.role == "ai")
                )
                if self.run_id:
                    stmt = stmt.where(Message.run_id == self.run_id)
                stmt = stmt.order_by(desc(Message.sequence_number)).limit(1)

                result = await session.execute(stmt)
                last_msg = result.scalar_one_or_none()

                if last_msg:
                    # Serialize steps (strip non-essential fields like start_time)
                    serialized_steps = [
                        {
                            "id": t.get("id"),
                            "name": t.get("name"),
                            "status": t.get("status"),
                            "type": t.get("type"),
                            "time": t.get("time"),
                            "details": t.get("details"),
                        }
                        for t in steps
                    ]
                    last_msg.steps_snapshot = serialized_steps
                    # session commits on exit
        except Exception:
            # Non-critical - don't crash the run
            pass
