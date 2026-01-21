import asyncio
import json
import re
import time
from typing import Any
from uuid import UUID
from sqlalchemy import desc, select

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import Message
from app.infrastructure.external.evocloud import evocloud_client
from app.schemas.events import MessageEvent


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

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        pass

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
                                if evocloud_client:
                                    asyncio.create_task(evocloud_client.update_task_status(task_id, 3, 100))

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
        await self._save_log(
            role="tool",
            content=str(output),
            status="completed",
            tool_output=str(output),
        )

    async def _save_log(
        self,
        role: str,
        content: str,
        thinking: str = None,
        status: str = "completed",
        references: list[dict] = None,
        tool_calls: list = None,
        tool_output: str = None,
    ):
        if not content and not thinking and not tool_calls:
            return

        # Improved Deduplication: Hash + Role + Time Window (2 seconds)
        # This allows legitimately repeated messages while preventing rapid-fire duplicates
        current_time = time.time()
        current_hash = hash((role, content, str(tool_calls))) if content else 0

        last_hash = getattr(self, "_last_logged_hash", None)
        last_time = getattr(self, "_last_logged_time", 0)

        # Dedup: Same hash AND role within 2 second window
        if current_hash == last_hash and (current_time - last_time) < 2.0:
            return

        self._last_logged_hash = current_hash
        self._last_logged_time = current_time

        try:
            self._sequence_counter += 1
            async with session_scope() as session:
                # Phase 4: Threading - Find parent (Last message in thread)
                # Ideally we should pass parent_id explicitly, but for now linear threading is fine.
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
                    # Phase 3: Message-Run Association
                    run_id=self.run_id,
                    status=status,
                    # Phase 4: Threading
                    parent_id=parent_id,
                    # Tool Data
                    tool_calls=tool_calls,
                    tool_output=tool_output,
                )
                session.add(log)
                await session.flush()  # Get ID

                # Phase 11: Real-time History Sync
                try:
                    # Access activity_monitor lazily to avoid circular imports at module level
                    from app.core.monitoring.activity import activity_monitor

                    # Serialize minimal data needed for frontend append
                    msg_data = {
                        "id": str(log.id),
                        "role": log.role,
                        "content": log.content,
                        # "created_at": log.created_at.isoformat() if log.created_at else None, # Created_at might be None until commit?
                        # Use current time if None?
                        "thinking": log.thinking,
                        "type": "text",
                        "tool_calls": log.tool_calls,  # Phase 24: Support Frontend Folding
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
                    from app.infrastructure.database.sql.models import MessageReference

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
