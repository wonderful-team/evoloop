
import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.markdown import Markdown

# Initialize a global console
console = Console()

class TransparentCallbackHandler(BaseCallbackHandler):
    """
    A CallbackHandler that uses 'rich' to render LLM thoughts, tool calls, 
    and code generation in real-time on the console.
    """

    def __init__(self, thread_id: str = None):
        super().__init__()
        self.thread_id = thread_id
        from app.core.monitoring.activity import activity_monitor
        self.monitor = activity_monitor
        self.current_task_id = None

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """Run when LLM starts running. Create a literal 'Thinking' task to visualize progress."""
        if self.thread_id and self.monitor:
            # Create a task for the AI generation
            self.current_task_id = self.monitor.add_task(self.thread_id, "Typing...", "ai")
            
    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Run on new LLM token. Stream into current task details."""
        console.print(token, end="", style="cyan")
        
        # Update monitor task details with streamed content
        if self.thread_id and self.current_task_id and self.monitor:
            # We need to append. But update_task replaces details.
            # Strategy: We rely on monitor state (or check if we need to cache it here).
            # ActivityMonitor doesn't expose 'append'.
            # Efficiently, we should accumulate locally.
            if not hasattr(self, '_current_stream_buffer'):
                self._current_stream_buffer = ""
            
            self._current_stream_buffer += token
            
            # Throttle updates? Every 5 tokens or so to save performance? 
            # For now, let's update every token for maximum responsiveness (polling is slow anyway).
            self.monitor.update_task(
                self.thread_id, 
                self.current_task_id, 
                "running", 
                details=self._current_stream_buffer
            )

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        console.print("\n")
        
        if self.thread_id and self.current_task_id and self.monitor:
             self.monitor.update_task(self.thread_id, self.current_task_id, "done")
             self.current_task_id = None
             if hasattr(self, '_current_stream_buffer'):
                 del self._current_stream_buffer

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Run when tool starts running."""
        tool_name = serialized.get("name")
        console.print(Panel(
            Text(f"Tool Call: {tool_name}\nInput: {input_str}", style="yellow"),
            title="[bold yellow]Worker Action[/bold yellow]",
            border_style="yellow"
        ))
        
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
                        self.monitor.update_agent_state(self.thread_id, mode, tname, tstatus)
                except:
                    pass
            
            # 2. Handle Artifacts
            if tool_name in ["write_to_file", "write_file", "create_file", "replace_file_content", "multi_replace_file_content"]:
                try:
                    # input_str might be JSON or direct string
                    if input_str.strip().startswith("{"):
                        data = json.loads(input_str)
                        # Check various keys
                        fname = data.get("TargetFile") or data.get("target_file") or data.get("filename") or data.get("file_path")
                        if fname:
                             self.monitor.add_artifact(self.thread_id, fname.split("/")[-1], "file", "pending", fname)
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

            self.current_task_id = self.monitor.add_task(self.thread_id, friendly_name, "tool")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Run when tool ends running."""
        if self.thread_id and self.current_task_id:
             self.monitor.update_task(self.thread_id, self.current_task_id, "done")
             self.current_task_id = None
             
             # If it was a write, mark artifact as modified/created
             # We rely on on_tool_start to have caught the name. 
             # Refinement: We could parse output to confirm success, but let's assume success for now.

        # Determine if output is long...
        if "```" in output or len(output) > 500:
            console.print(Panel(
                Markdown(output),
                title="[bold white]Tool Output[/bold white]",
                border_style="white"
            ))
        else:
            console.print(Panel(
                Text(output, style="white"),
                title="[bold white]Tool Output[/bold white]",
                border_style="white"
            ))

    def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> None:
        """Run when chain starts running."""
        pass
        
    def on_text(self, text: str, **kwargs: Any) -> None:
        """Run on arbitrary text."""
        console.print(text)
