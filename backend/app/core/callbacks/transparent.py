
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
        self._current_stream_buffer = ""

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """Run when LLM starts running."""
        # logger.info("LLM Start") # Too noisy
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)
            self.current_task_id = await self.monitor.add_task(self.thread_id, "Typing...", "ai")
            
    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        # Avoid logging every token to file!
        # console.print(token, end="", style="cyan") 
        
        # Check cancellation during streaming
        if self.thread_id and self.monitor:
             await self.monitor.check_cancellation(self.thread_id)
        
        # Update monitor task details with streamed content
        if self.thread_id and self.current_task_id and self.monitor:
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
        
        if self.thread_id and self.current_task_id and self.monitor:
             await self.monitor.update_task(self.thread_id, self.current_task_id, "done")
             self.current_task_id = None
             self._current_stream_buffer = ""

    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Run when tool starts running."""
        # Check cancellation
        if self.thread_id and self.monitor:
            await self.monitor.check_cancellation(self.thread_id)

        tool_name = serialized.get("name")
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
        # Truncate output logging to avoid spam
        log_output = output  # [:1000] + "..." if len(output) > 1000 else output
        logger.info(f"[Tool End] Output: {log_output}")

    async def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> None:
        """Run when chain starts running."""
        pass
        
    async def on_text(self, text: str, **kwargs: Any) -> None:
        """Run on arbitrary text."""
        logger.info(f"[Text] {text}")
