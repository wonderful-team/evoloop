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
    def __init__(self, thread_id: str, project_id: int):
        self.thread_id = thread_id
        self.project_id = project_id

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
                    content = md

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
        
        # Simple heuristic: If it contains "Error" or "Exception" or "Failed"
        # AND it's short enough to be a message.
        if "error" in content.lower() or "exception" in content.lower() or "failed" in content.lower():
             # It might be an error. Log it.
             # Clean up a bit
             if len(content) > 500:
                  content = content[:500] + "... (truncated)"
             
             await self._save_log("tool", f"❌ **Tool Error:** {content}")
        else:
            # Success (presumably). Skip logging to DB.
            # The 'Action' log from on_llm_end covers the intent.
            pass

    def _get_tool_summary(self, tool_call: Dict) -> str:
        t_name = tool_call.get("name", "tool")
        t_args = tool_call.get("args", {})
        
        try:
            if t_name in ["write_file", "replace_file_content", "write_to_file"]:
                path = t_args.get("target_file") or t_args.get("TargetFile") or t_args.get("file_path") or "unknown"
                path_parts = path.split("/")
                short_path = "/".join(path_parts[-2:]) if len(path_parts) > 1 else path
                
                # Try to count lines?
                content = t_args.get("code_content") or t_args.get("replacement_content") or ""
                lines = len(content.splitlines()) if content else 0
                return f"Writing `{short_path}` ({lines} lines)"
                
            elif t_name in ["read_document", "read_file", "view_file"]:
                path = t_args.get("file_path") or t_args.get("AbsolutePath") or t_args.get("url") or "unknown"
                path_parts = path.split("/")
                short_path = "/".join(path_parts[-2:]) if len(path_parts) > 1 else path
                return f"Reading `{short_path}`"
                
            elif t_name == "run_command":
                cmd = t_args.get("command_line") or t_args.get("CommandLine") or "unknown"
                return f"Running: `{cmd}`"
                
            elif t_name == "create_plan":
                title = t_args.get("title", "Untitled")
                steps = t_args.get("steps", [])
                return f"Creating Plan: **{title}** ({len(steps)} steps)"
                
            elif t_name in ["search_codebase", "grep_search"]:
                query = t_args.get("query") or "unknown"
                return f"Searching: `{query}`"
                
            return f"Calling `{t_name}`"
        except:
            return f"Calling `{t_name}`"

    async def _save_log(self, role: str, content: str, thinking: str = None):
        if not content and not thinking:
            return

        try:
             async with session_scope() as session:
                 log = Message(
                     thread_id=self.thread_id,
                     project_id=self.project_id,
                     role=role,
                     content=content,
                     thinking=thinking
                 )
                 session.add(log)
                 # session_scope commits automatically
        except Exception as e:
            # logger.error(f"Failed to log message: {e}")
            pass
