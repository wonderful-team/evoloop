
import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
import json

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

# Use standard logger instead of rich Console
logger = logging.getLogger("evoloop.callbacks")

class TransparentCallbackHandler(AsyncCallbackHandler):
    """
    A CallbackHandler that logs LLM thoughts, tool calls, 
    and code generation to standard logger.
    Async compliant for Redis Monitor integration.
    """

    def __init__(self, thread_id: str = None):
        super().__init__()
        self.thread_id = thread_id
        from app.core.monitoring.activity import activity_monitor
        self.monitor = activity_monitor
        self.current_task_id = None
        self.active_llm_run_id = None
        self._current_stream_buffer = ""

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """Run when LLM starts running."""
    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """Run when LLM starts running."""
        # logger.info("LLM Start") # Too noisy
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)
            
            # Deduplicate nested LLM calls
            # Only start a "Thinking..." task if no LLM is currently active for this handler
            if self.active_llm_run_id is None:
                self.active_llm_run_id = kwargs.get("run_id")
                self.current_task_id = await self.monitor.add_task(self.thread_id, "Thinking...", "ai")
            
    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        # Avoid logging every token to file!
        # console.print(token, end="", style="cyan") 
        
        # Check cancellation during streaming
        if self.thread_id and self.monitor:
             await self.monitor.check_cancellation(self.thread_id)
        
        # Update monitor task details with streamed content
        # Ensure we only update for the active run
        run_id = kwargs.get("run_id")
        if self.thread_id and self.current_task_id and self.monitor:
            if run_id == self.active_llm_run_id:
                self._current_stream_buffer += token
                await self.monitor.update_task(
                    self.thread_id, 
                    self.current_task_id, 
                    "running", 
                    details=self._current_stream_buffer
                )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        # logger.info("LLM End")
        
        run_id = kwargs.get("run_id")
        if self.thread_id and self.current_task_id and self.monitor:
             # Only close if the ending run is the one that started the task
             if run_id == self.active_llm_run_id:
                 await self.monitor.update_task(self.thread_id, self.current_task_id, "done")
                 self.current_task_id = None
                 self.active_llm_run_id = None
                 self._current_stream_buffer = ""

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when LLM errors."""
        logger.error(f"LLM Error in thread {self.thread_id}: {error}", exc_info=True)
        
        run_id = kwargs.get("run_id")
        if self.thread_id and self.current_task_id and self.monitor:
             if run_id == self.active_llm_run_id:
                 await self.monitor.update_task(self.thread_id, self.current_task_id, "failed", details=str(error))
                 self.current_task_id = None
                 self.active_llm_run_id = None
                 self._current_stream_buffer = ""

    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Run when tool starts running."""
        # Check cancellation
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

        tool_name = serialized.get("name")
        self.current_tool_name = tool_name
        self.current_tool_path = None
        
        # Try to extract file path for read operations
        # Fix: Support manage_file with action='read'
        if tool_name in ["read_file", "view_file", "read_file_content", "manage_file"]:
            import json
            import ast
            
            data = None
            try:
                # Agent inputs are often JSON strings
                if input_str.strip().startswith("{"):
                     data = json.loads(input_str)
            except:
                pass

            # Fallback: LangChain sometimes logs inputs as Python dict string (single quotes)
            if data is None:
                try:
                    if input_str.strip().startswith("{"):
                        data = ast.literal_eval(input_str)
                except:
                    pass

            if data and isinstance(data, dict):
                 path = None
                 
                 if tool_name == "manage_file":
                     if data.get("action") == "read":
                         path = data.get("path")
                 else:
                     path = data.get("AbsolutePath") or data.get("file_path") or data.get("path") or data.get("TargetFile")

                 if path:
                     self.current_tool_path = path

        # Standard Log Output
        logger.info(f"[Tool Start] {tool_name} Input: {input_str[:500]}...")
        
        if self.thread_id:
            import json
            
            # 1. Handle Task Boundary (Agent State)
            if tool_name == "task_boundary":
                try:
                    data = json.loads(input_str)
                    mode = data.get("Mode")
                    tname = data.get("TaskName")
                    tstatus = data.get("TaskStatus")
                    if mode and tname:
                        await self.monitor.update_agent_state(self.thread_id, mode, tname, tstatus)
                except:
                    pass
            
            # 2. Handle Artifacts
            if tool_name in ["write_to_file", "write_file", "create_file", "replace_file_content", "multi_replace_file_content"]:
                try:
                    if input_str.strip().startswith("{"):
                        data = json.loads(input_str)
                        fname = data.get("TargetFile") or data.get("target_file") or data.get("filename") or data.get("file_path")
                        if fname:
                             await self.monitor.add_artifact(self.thread_id, fname.split("/")[-1], "file", "pending", fname)
                except:
                    pass
            
            # 3. Create Task (Friendly Name)
            friendly_name = f"Using {tool_name}"
            if tool_name == "task_boundary":
                friendly_name = "Updating Task Status"
            elif tool_name == "write_to_file":
                friendly_name = "Writing File"
            elif tool_name == "replace_file_content":
                friendly_name = "Modifying File"
            elif tool_name == "run_command":
                try:
                    data = json.loads(input_str)
                    cmd = data.get("CommandLine")
                    if cmd:
                        friendly_name = f"Running: {cmd[:30]}..."
                except:
                    friendly_name = "Running Command"

            self.current_task_id = await self.monitor.add_task(self.thread_id, friendly_name, "tool")

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Run when tool ends running."""
        if self.thread_id and self.current_task_id:
             await self.monitor.update_task(self.thread_id, self.current_task_id, "done")
             self.current_task_id = None
             
        # Standard Log Output
        # Strict sanitation for file reads (including manage_file read)
        log_output = output
        
        is_read_tool = self.current_tool_name in ["read_file", "view_file", "read_file_content"]
        is_manage_read = (self.current_tool_name == "manage_file" and self.current_tool_path)
        
        if (is_read_tool or is_manage_read) and self.current_tool_path:
             lines = output.split('\n')
             count = len(lines)
             if not output: count = 0
             log_output = f"File: {self.current_tool_path} (Lines: {count})"
        
        elif len(output) > 500:
             lines = output.split('\n')
             if len(lines) > 20:
                 log_output = f"{output[:300]}\n...\n[Truncated {len(lines)} lines / {len(output)} chars]"
        
        logger.info(f"[Tool End] Output: {log_output}")

    async def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> None:
        """Run when chain starts running."""
        # 1. Check for LangGraph Node Transition
        # LangGraph injects 'langgraph_node' into metadata
        metadata = kwargs.get("metadata", {})
        node_name = metadata.get("langgraph_node")
        
        if node_name and self.thread_id and self.monitor:
             # Ignore internal nodes/pregel stuff if necessary
             # Usually node names are meaningful (e.g. "tech_lead", "coder")
             
             # Avoid "Start" / "End" noise if possible, but LangGraph usually names them specifically
             
             # Add a "Section" task
             # We use type="node" (or "section") 
             # For now "node" matches generic logic
             friendly_name = f"Entering [{node_name}]"
             
             # Auto-close previous node tasks? 
             # ActivityMonitor supports hierarchical tasks? No, flat list.
             # So we just append this as a milestone.
             # We mark it as 'done' immediately? Or leave it running until next node?
             # If we leave it running, we need to track it to close it.
             # But on_chain_end triggers for this node too?
             # Yes, on_chain_end should trigger. 
             # Let's track it.
             
             # Store node_run_id -> task_id map? 
             # We only have one `current_task_id` in this handler class.
             # But on_chain_start nests.
             # If we overwrite `current_task_id`, we lose the previous one (e.g. LLM call inside Node).
             # Wait, Node is the wrapper. LLM runs INSIDE Node.
             # sequence: Node Start -> LLM Start -> LLM End -> Node End.
             
             # So:
             # 1. Node Start: Set `current_node_task_id`? 
             # We might need a stack if we want perfect nesting.
             # But for MVP, let's just log "Entering X" and mark it done immediately?
             # Or mark it "running" and close it on_chain_end?
             
             # Let's try marking it running.
             run_id = kwargs.get("run_id")
             task_id = await self.monitor.add_task(self.thread_id, friendly_name, "node")
             
             # We can't easily track multiple active tasks with just one variable.
             # But this handler instance is per run? No, standard callback handler is reused?
             # Actually, usually one handler per invoke? Or global?
             # In our code, we init `TransparentCallbackHandler(thread_id)` for the run.
             # So it persists.
             
             # If we want to close it properly on_chain_end, we need to map run_id -> (task_id, node_name).
             if not hasattr(self, "_active_nodes"):
                 self._active_nodes = {}
             
             self._active_nodes[run_id] = (task_id, node_name)
             
    async def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Run when chain ends running."""
        run_id = kwargs.get("run_id")
        if hasattr(self, "_active_nodes") and run_id in self._active_nodes:
            task_id, node_name = self._active_nodes[run_id]
            if self.thread_id and self.monitor:
                # 1. Update the original node task to 'done'
                await self.monitor.update_task(self.thread_id, task_id, "done")
                
                # 2. Emit an "Exiting" milestone to trigger frontend stack pop
                # This is crucial for TaskSteps auto-collapse and hierarchy logic
                exit_name = f"Exiting [{node_name}]"
                await self.monitor.add_task(self.thread_id, exit_name, "node", status="done")
                
            del self._active_nodes[run_id]

    async def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when chain errors."""
        run_id = kwargs.get("run_id")
        if hasattr(self, "_active_nodes") and run_id in self._active_nodes:
            task_id, node_name = self._active_nodes[run_id]
            if self.thread_id and self.monitor:
                # 1. Update the original node task to 'failed'
                await self.monitor.update_task(self.thread_id, task_id, "failed", details=str(error))
                
                # 2. Emit an "Exiting" milestone with 'failed' status
                exit_name = f"Exiting [{node_name}]"
                await self.monitor.add_task(self.thread_id, exit_name, "node", status="failed")
                
            del self._active_nodes[run_id]
        
    async def on_text(self, text: str, **kwargs: Any) -> None:
        """Run on arbitrary text."""
        logger.info(f"[Text] {text}")
