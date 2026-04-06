import asyncio
import json
import logging
import re
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from app.infrastructure.queue.factory import get_scheduler
from app.core.config import settings
from app.core.context import tool_state_store
from app.core.evocloud import evocloud_manager
from app.i18n.service import i18n
from app.models.schemas.events import MessageEvent
from app.core.tools.registry import get_tool_metadata

logger = logging.getLogger(__name__)


class DatabaseCallbackHandler(AsyncCallbackHandler):
    """
    Callback Handler that logs user-friendly messages to the database.
    Acts as a View Layer sanitizer.
    
    Implements "Real-time Attribution" (方案 A): Steps are attributed to the 
    AI message that was active when they were executed, rather than all 
    accumulating on the final summary message.
    """

    def __init__(self, thread_id: str, project_id: int, start_sequence: int = 0, run_id: str = None):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id  # Associate messages with specific execution runs
        self._sequence_counter = start_sequence  # Track message order within thread
        self._tool_store = tool_state_store
        self._last_attributed_step_index = 0  # Track which steps have been attributed

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        pass

    async def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any) -> Any:
        """Track which tool is running for a given run_id."""
        tool_name = serialized.get("name")
        
        # Skip hidden/internal tools
        if tool_name:
            visibility = self._get_tool_visibility(tool_name)
            if visibility == "HIDDEN":
                return
        
        if tool_name and self.thread_id:
            self._tool_store.start_tool(
                thread_id=self.thread_id,
                run_id=str(run_id),
                name=tool_name,
                arguments=input_str,
                path=None
            )

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

            # 1. Parse Thinking (<think>)
            thinking = None
            think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL | re.IGNORECASE)
            if think_match:
                thinking = think_match.group(1).strip()
                content = content.replace(think_match.group(0), "").strip()

            # 1.1 Parse Audit (<audit>) - Implementation of structured audit separation
            # We move audit results to the 'thinking' field so they are stored but not shown as main chat content.
            audit_match = re.search(r"<audit>(.*?)</audit>", content, re.DOTALL | re.IGNORECASE)
            if audit_match:
                audit_content = audit_match.group(1).strip()
                # Append to 'thinking' if thinking already exists (e.g. from <think> tag)
                if thinking:
                    thinking = f"{thinking}\n\n--- Audit ---\n{audit_content}"
                else:
                    thinking = audit_content
                content = content.replace(audit_match.group(0), "").strip()

            # 1.2 Parse Report (<report>) - Extract report as primary content
            report_match = re.search(r"<report>(.*?)</report>", content, re.DOTALL | re.IGNORECASE)
            if report_match:
                content = report_match.group(1).strip()
            
            # 1.3 Cleanup: Remove any other technical XML tags (like <thought>, <status>, etc.)
            content = re.sub(r"<[^>]+>", "", content).strip()

            # 1.5 Filter out technical 'SESSION COMPLETE' messages from chat history.
            # These are critical for Imitation Learning but should not be shown to users.
            if content and (content.strip().startswith("✅ SESSION COMPLETE") or content.strip().startswith("❌ SESSION COMPLETE")):
                logger.info(f"[DatabaseCallbackHandler] Filtering technical session review from chat: {self.thread_id}")
                return

            # 2. Detect and Format JSON (Supervisor/Router Outputs)
            if content and content.strip().startswith("{") and content.strip().endswith("}"):
                try:
                    data = json.loads(content)
                    # Case A: Routing Decision
                    if "next_node" in data:
                        node = data.get("next_node")
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
                        content = i18n.get("database_logger.decision", node=node)
                    
                    # Case C: Internal Structured data (Skill Discovery, Decomposition, etc.)
                    # If it's JSON but not a recognized UI-friendly format, SILENTLY ignore it
                    elif any(key in data for key in ["match_found", "skill_id", "subtasks", "can_parallelize"]):
                        logger.info(f"[DatabaseCallbackHandler] Suppressing internal JSON leakage: {list(data.keys())}")
                        return

                except Exception:
                    pass

            # Persist to DB
            tool_calls = getattr(message, "tool_calls", None)
            
            # Filter hidden/internal tools from tool_calls - they are internal control signals
            # and should not be persisted as they are not user-facing operations.
            if tool_calls:
                visible_tool_calls = [
                    tc for tc in tool_calls 
                    if not (get_tool_metadata(tc.get("name")) or {}).get("is_hidden", False)
                ]
                tool_calls = visible_tool_calls if visible_tool_calls else None
            
            # 👇 提取 node_source 用于语音播报过滤
            node_source = None
            if hasattr(message, "metadata") and message.metadata:
                node_source = message.metadata.get("node_source")
            
            # Before saving new AI message, attribute pending steps to the previous AI message
            # This implements "Real-time Attribution" (方案 A)
            await self._attribute_pending_steps_to_previous_message()
            
            await self._save_log(
                role="ai",  # Normalized role value
                content=content,
                thinking=thinking,
                tool_calls=tool_calls,
                node_source=node_source,  # 👈 传递节点来源
            )

        except Exception:
            # Swallow errors in logging to prevent crashing the flow
            pass

    def _get_tool_summary(self, tool_call: dict) -> str:
        """Generate a user-friendly summary of what a tool is doing."""
        tool_name = tool_call.get("name", "tool")
        tool_input = tool_call.get("args", {})
        metadata = get_tool_metadata(tool_name) or {}

        # 1. Use Metadata-driven summary template if available
        summary_template = metadata.get("summary_template")
        if summary_template:
            try:
                # Merge tool_input into i18n keys if they use formatting, or pass as kwargs
                return i18n.get(summary_template, **tool_input)
            except Exception:
                # Fallback if i18n interpolation fails due to missing keys in tool_input
                pass

        # Fallback to default running tool summary
        return i18n.get("database_logger.tool_summary.default", tool=tool_name)

    def _extract_reference(self, tool_call: dict) -> dict | None:
        """Extract structure reference data from tool call"""
        t_name = tool_call.get("name", "tool")
        t_args = tool_call.get("args", {})
        metadata = get_tool_metadata(t_name) or {}

        try:
            # 1. Metadata-driven path extraction (Affected Paths)
            affected_keys = metadata.get("affected_path_keys", [])
            if affected_keys:
                # Find the first available path
                for key in affected_keys:
                    path = t_args.get(key)
                    if path and isinstance(path, str):
                        name = path.split("/")[-1]
                        return {"type": "file", "target_id": path, "target_name": name}

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
        tool_state = None
        if self.thread_id:
            tool_state = self._tool_store.end_tool(self.thread_id, run_id_str)
        
        tool_name = tool_state.name if tool_state else "unknown_tool"

        visibility = self._get_tool_visibility(tool_name)
        if visibility == "HIDDEN":
            return

        # 2. Process Content (Folding/Summarizing)
        # Store raw tool output with action_type='tool_output' for frontend rendering.
        # Frontend handles display logic (Accordion).

        await self._save_log(
            role="tool",
            content=str(output),
            status="completed",
            action_type="tool_output",
        )

    def _get_tool_visibility(self, tool_name: str) -> str:
        """
        Determine tool visibility for database logging.
        
        HIDDEN: Internal control flow tools that should not be recorded.
        VISIBLE: User-facing tools that should be logged.
        """
        from app.core.tools.registry import get_tool_metadata
        
        metadata = get_tool_metadata(tool_name) or {}
        if metadata.get("is_hidden", False):
            return "HIDDEN"

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
        action_type: str = "text",
        node_source: str | None = None,  # 👈 添加节点来源参数
    ):
        # Sanitize content for PostgreSQL (remove NUL bytes)
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
            # Parent ID and DB Persistence now offloaded to Celery background task
            # to prevent blocking the agent loop with IO.

            # Send to Background
            get_scheduler().send_task(
                "engine_persist_message",
                kwargs={
                    "thread_id": self.thread_id,
                    "project_id": self.project_id,
                    "role": role,
                    "content": content,
                    "thinking": thinking,
                    "sequence_number": self._sequence_counter,
                    "run_id": self.run_id,
                    "status": status,
                    "tool_calls": tool_calls,
                    "references": references,
                    "action_type": action_type,
                }
            )

            # Real-time History Sync (Non-blocking cache publish)
            try:
                from app.core.monitoring.activity import activity_monitor

                # Map action_type to frontend type
                frontend_type = "text"
                if role == "human":
                    frontend_type = "human"
                elif action_type == "tool_output":
                    frontend_type = "tool"
                elif action_type == "thinking":
                    frontend_type = "thought"

                msg_data = {
                    "id": f"temp-{time.time()}",  # Temp ID for UI, DB id will follow
                    "role": role,
                    "content": content,
                    "thinking": thinking,
                    "type": frontend_type,
                    "action_type": action_type,
                    "tool_calls": tool_calls,
                    "node_source": node_source,  # 👈 添加节点来源，用于前端语音播报过滤
                }

                # Fire and forget
                if activity_monitor and hasattr(activity_monitor, "client"):
                    try:
                        client = activity_monitor.client
                        channel = f"chat:{self.thread_id}:events"
                        message = MessageEvent(data=msg_data).model_dump_json()
                        logger.debug(f"[DatabaseCallback] Publishing to {channel}: {message}")
                        result = await client.publish(channel, message)
                        logger.debug(f"[DatabaseCallback] Publish result: {result}")
                    except Exception as e:
                        logger.warning(f"[DatabaseCallback] Failed to publish message event: {e}", exc_info=True)
            except Exception as e:
                logger.warning(f"[DatabaseCallback] Failed in realtime sync setup: {e}", exc_info=True)

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"CRITICAL: Failed to publish message event or offload to background: {e}", exc_info=True)
            # We don't re-raise to avoid killing the agent execution loop,
            # but this error will now be visible in logs.

    async def _attribute_pending_steps_to_previous_message(self):
        """
        Attribute pending steps from Activity Monitor to the previous AI message.
        
        This implements "Real-time Attribution" (方案 A): Instead of accumulating
        all steps on the final summary message, steps are attributed to the AI 
        message that was active when they were executed.
        """
        if not self.thread_id:
            return
        
        try:
            from app.core.monitoring.activity import activity_monitor
            
            # Get current activity state including all steps
            activity_data = await activity_monitor.get_activity(self.thread_id)
            all_steps = activity_data.get("steps", [])
            
            # Find new steps since last attribution
            new_steps = all_steps[self._last_attributed_step_index:]
            
            if new_steps:
                # Update our tracker before sending to Celery
                self._last_attributed_step_index = len(all_steps)
                
                # Send to background task to attribute to previous message
                # Uses the same task as final snapshot, but now it appends instead of overwrites
                get_scheduler().send_task(
                    "engine_snapshot_steps",
                    kwargs={
                        "thread_id": self.thread_id,
                        "project_id": self.project_id,
                        "run_id": self.run_id,
                        "steps": new_steps
                    }
                )
                logger.debug(f"[DatabaseCallback] Attributed {len(new_steps)} steps to previous message")
        except Exception as e:
            logger.warning(f"[DatabaseCallback] Failed to attribute pending steps: {e}")

    async def snapshot_steps_to_last_message(self, steps: list):
        """
        Persist executed steps to the last AI message for historical rendering.
        Offloaded to Celery to avoid blocking the agent loop.
        
        EMBEDDED_MODE: Waits for task completion to ensure data is persisted
        before the agent loop exits (LocalCelery is fire-and-forget otherwise).
        """
        if not steps:
            return

        try:
            result = get_scheduler().send_task(
                "engine_snapshot_steps",
                kwargs={
                    "thread_id": self.thread_id,
                    "project_id": self.project_id,
                    "run_id": self.run_id,
                    "steps": steps
                }
            )

            # EMBEDDED_MODE: Wait for task completion to ensure data persistence
            # LocalCelery uses fire-and-forget by default, which can lose tasks
            # when the event loop closes at agent shutdown
            if settings.EMBEDDED_MODE:
                logger.info(f"[DatabaseCallback] EMBEDDED_MODE detected: Waiting for steps snapshot task...")
                await result.get(timeout=10)

        except Exception as e:
            logger.warning(f"Failed to snapshot steps: {e}")
