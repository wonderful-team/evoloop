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
                    # Fix: Keep a summary in content so it's not empty
                    thinking = md
                    if not content or content.strip().startswith("{"):
                         content = f"🤔 **Thinking Process:**\n{reasoning}\n\n(See Thinking tab for details)"


            except json.JSONDecodeError:
                pass # Not JSON, ignore
            
        # 3. Save if we have content or thinking
        if content or thinking:
             # Phase 9: Extract References from tool calls
             references = []
             tool_calls_data = None
             
             if hasattr(message, "tool_calls") and message.tool_calls:
                 tool_calls_data = [tc for tc in message.tool_calls] # Copy list
                 for tc in message.tool_calls:
                     ref = self._extract_reference(tc)
                     if ref:
                         references.append(ref)
             
             # Determine Role: If pure tool call (no text content), log as 'tool' to hide from UI
             # But if mixed (Text + Action), keep as 'ai'
             log_role = "ai"
             original_text_content = generation.message.content or ""
             if not original_text_content.strip() and hasattr(message, "tool_calls") and message.tool_calls:
                 log_role = "tool"

             await self._save_log(log_role, content, thinking=thinking, references=references, tool_calls=tool_calls_data)

    def _get_tool_summary(self, tool_call: Dict) -> str:
        """Generate a user-friendly summary of what a tool is doing."""
        tool_name = tool_call.get("name", "tool")
        tool_input = tool_call.get("args", {})
        
        if tool_name == "manage_file":
            action = tool_input.get("action", "access")
            path = tool_input.get("path", "file")
            return f"{action.replace('_', ' ').capitalize()} '{path}'"
        elif tool_name == "search_codebase":
            query = tool_input.get("query", "")
            return f"Searching code for '{query}'"
        elif tool_name == "request_human_input":
            return f"Asking user: {tool_input.get('prompt', '')}"
        
        return f"Running {tool_name}"

    def _extract_reference(self, tool_call: Dict) -> Optional[Dict]:
        """Extract structure reference data from tool call"""
        t_name = tool_call.get("name", "tool")
        t_args = tool_call.get("args", {})
        
        try:
            if t_name in ["read_document", "read_file", "view_file", "manage_file"]:
                 path = t_args.get("file_path") or t_args.get("AbsolutePath") or t_args.get("url") or t_args.get("path") or "unknown"
                 name = path.split("/")[-1]
                 return {"type": "file", "target_id": path, "target_name": name}
            
            elif t_name in ["search_codebase", "grep_search", "find_by_name"]:
                 query = t_args.get("query") or t_args.get("Pattern") or "unknown"
                 return {"type": "knowledge", "target_id": query, "target_name": f"Search: {query}"}
                 
            elif t_name == "read_memory_item": # Hypothetical tool for memory
                 mem_id = t_args.get("id", "unknown")
                 return {"type": "memory", "target_id": mem_id, "target_name": "Memory Item"}
            
            return None
        except:
            return None

    # Implement on_tool_end to capture tool outputs
    async def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        # Capture tool output
        # Used for history and debugging
        await self._save_log(role="tool", content=str(output), status="completed", tool_output=str(output))

    async def _save_log(self, role: str, content: str, thinking: str = None, status: str = "completed", references: List[Dict] = None, tool_calls: List = None, tool_output: str = None):
        if not content and not thinking and not tool_calls:
            return

        # Improved Deduplication: Hash + Role + Time Window (2 seconds)
        # This allows legitimately repeated messages while preventing rapid-fire duplicates
        import time
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
                 from sqlalchemy import select, desc
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
                     tool_output=tool_output
                 )
                 session.add(log)
                 await session.flush() # Get ID

                 # Phase 9: Save References
                 if references:
                     from app.infrastructure.database.sql.models import MessageReference
                     for ref in references:
                         mr = MessageReference(
                             id=str(UUID(int=hash(f"{log.id}-{ref['target_id']}-{time.time()}") & ((1<<128)-1))), # Pseudo UUID
                             message_id=log.id,
                             type=ref["type"],
                             target_id=ref["target_id"],
                             target_name=ref["target_name"]
                         )
                         session.add(mr)

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
