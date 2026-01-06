from typing import Any, Dict, List, Optional
from uuid import UUID
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import Message
import asyncio

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
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        pass

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        if not response.generations:
            return

        generation = response.generations[0][0]
        message = generation.message # type: ignore
        content = message.content or ""
        
        # 1. Parse Thinking
        import re
        thinking = None
        think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
        if think_match:
            thinking = think_match.group(1).strip()
            content = content.replace(think_match.group(0), "").strip()
            
        # 2. Enhance with Tool Summaries
        if hasattr(message, "tool_calls") and message.tool_calls:
            summaries = []
            for tc in message.tool_calls:
                summaries.append(self._get_tool_summary(tc))
            
            if summaries:
                summary_block = "**Action:**\n" + "\n".join([f"- {s}" for s in summaries])
                if content:
                    content = f"{content}\n\n{summary_block}"
                else:
                    content = summary_block
        
        # 3. Detect and Format JSON (Supervisor/Router Outputs)
        import json
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
                         import re
                         task_match = re.search(r"task-(\d+)-", self.thread_id)
                         if task_match:
                             task_id = int(task_match.group(1))
                             from app.infrastructure.external.imagicbox import imagicbox_client
                             # STATUS_COMPLETED = 3, Progress = 100
                             await imagicbox_client.update_task_status(task_id, 3, 100)
                             # Suppress local message logging
                             return
                        #  content = "✅ **Task Completed.**"
                    elif node == "map_research" and parallel:
                         tasks_str = ", ".join([f"`{t}`" for t in parallel])
                         content = f"**Decision:** Researching multiple topics in parallel: {tasks_str}"
                    else:
                         content = f"**Decision:** Routing to **{node}**."
                
                # Case B: Intent Analysis (from legacy or other nodes)
                elif "intent" in data and "reasoning" in data:
                    intent = data.get("intent")
                    reasoning = data.get("reasoning")
                    refined = data.get("refined_instruction")
                    
                    md = f"**Analysis:** {reasoning}\n"
                    md += f"**Intent:** `{intent}`"
                    if refined:
                        md += f"\n**Refined Goal:** {refined}"
                    
                    # Fix: Move this internal analysis to 'thinking' so it's collapsed in UI
                    # instead of showing as a main bubble.
                    thinking = md
                    content = ""

            except json.JSONDecodeError:
                pass # Not JSON, ignore
            
        # 3. Save if we have content or thinking
        if content or thinking:
             await self._save_log("ai", content, thinking=thinking)

    async def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """
        Only log tool outputs if they look like errors.
        Users don't need to see 'File read successfully' 100 times.
        """
        # output is usually a string, but could be Artifact?
        content = str(output)
        
        # Refined Heuristic:
        # 1. Must START with "Error:" or "Exception:" or "Failed:" (Case insensitive)
        # 2. OR be very short (< 200 chars) and contain "error" (to catch "FileNotFoundError" ecc)
        # 3. Explicitly ignore large content blocks (likely file reads)
        
        is_error = False
        lower_content = content.lower().strip()
        
        if len(content) > 500:
             # Large output is almost certainly NOT a tool execution error (it's data)
             is_error = False
        elif lower_content.startswith("error:") or lower_content.startswith("exception:") or lower_content.startswith("failed:"):
             is_error = True
        elif len(content) < 200 and ("error" in lower_content or "exception" in lower_content or "traceback" in lower_content):
             is_error = True
             
        if is_error:
             # It might be an error. Log it.
             await self._save_log("tool", f"❌ **Tool Error:** {content}")
        else:
            # Success (presumably). Skip logging to DB.
            # The 'Action' log from on_llm_end covers the intent.
            pass
            
    async def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> Any:
        """
        Capture Node Outputs (State Updates).
        This handles manually constructed messages from nodes like Tester/Coder/Finish.
        We filter specifically for 'messages' key to target Graph Node outputs.
        """
        if not isinstance(outputs, dict) or "messages" not in outputs:
            return

        ms_list = outputs["messages"]
        if not isinstance(ms_list, list):
            ms_list = [ms_list]

        from langchain_core.messages import AIMessage
        
        for msg in ms_list:
            # We only care about AI Messages (System/Human are inputs or internal)
            # And we only care if there is content.
            if isinstance(msg, AIMessage) and msg.content:
                # Deduplication logic is handled inside _save_log or implies distinct events.
                await self._save_log("ai", msg.content)

    def _get_tool_summary(self, tool_call: Dict) -> str:
        t_name = tool_call.get("name", "tool")
        t_args = tool_call.get("args", {})
        
        try:
            if t_name in ["write_file", "replace_file_content", "write_to_file", "multi_replace_file_content"]:
                path = t_args.get("target_file") or t_args.get("TargetFile") or t_args.get("file_path") or "unknown"
                path_parts = path.split("/")
                short_path = path_parts[-1] # Filename only
                
                return f"📝 Write `{short_path}`"
                
            elif t_name in ["read_document", "read_file", "view_file", "manage_file"]:
                # Check action for manage_file
                if t_name == "manage_file" and t_args.get("action") != "read":
                     action = t_args.get("action", "exec")
                     path = t_args.get("path") or "unknown"
                     return f"📁 FS: {action} `{path.split('/')[-1]}`"

                path = t_args.get("file_path") or t_args.get("AbsolutePath") or t_args.get("url") or t_args.get("path") or "unknown"
                short_path = path.split("/")[-1]
                return f"📄 Read `{short_path}`"
                
            elif t_name == "run_command":
                cmd = t_args.get("command_line") or t_args.get("CommandLine") or "unknown"
                # Truncate cmd
                return f"💻 Exec `{cmd[:40]}...`" if len(cmd) > 40 else f"💻 Exec `{cmd}`"
                
            elif t_name == "create_plan":
                title = t_args.get("title", "Untitled")
                return f"📅 Plan: {title}"
                
            elif t_name in ["search_codebase", "grep_search", "find_by_name"]:
                query = t_args.get("query") or t_args.get("Pattern") or "unknown"
                return f"🔍 Search `{query}`"
            
            elif t_name == "task_boundary":
                mode = t_args.get("Mode", "UPDATE")
                return f"📍 Task: {mode}"

            return f"🔧 {t_name}"
        except:
            return f"🔧 {t_name}"

    async def _save_log(self, role: str, content: str, thinking: str = None, status: str = "completed"):
        if not content and not thinking:
            return

        # Improved Deduplication: Hash + Role + Time Window (2 seconds)
        # This allows legitimately repeated messages while preventing rapid-fire duplicates
        import time
        current_time = time.time()
        current_hash = hash((role, content)) if content else 0
        
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
                 log = Message(
                     thread_id=self.thread_id,
                     project_id=self.project_id,
                     role=role,
                     content=content,
                     thinking=thinking,
                     sequence_number=self._sequence_counter,
                     # Phase 3: Message-Run Association
                     run_id=self.run_id,
                     status=status
                 )
                 session.add(log)
                 # session_scope commits automatically
        except Exception as e:
            # logger.error(f"Failed to log message: {e}")
            pass

    async def snapshot_tasks_to_last_message(self, tasks: list):
        """
        Phase 6: Persist task steps to the last AI message for historical rendering.
        Called when a run completes (done/failed/cancelled).
        """
        if not tasks:
            return
            
        try:
            from sqlalchemy import select, desc
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
                    # Serialize tasks (strip non-essential fields like start_time)
                    serialized_tasks = [
                        {
                            "id": t.get("id"),
                            "name": t.get("name"),
                            "status": t.get("status"),
                            "type": t.get("type"),
                            "time": t.get("time"),
                            "details": t.get("details")
                        }
                        for t in tasks
                    ]
                    last_msg.tasks_snapshot = serialized_tasks
                    # session commits on exit
        except Exception as e:
            # Non-critical - don't crash the run
            pass
