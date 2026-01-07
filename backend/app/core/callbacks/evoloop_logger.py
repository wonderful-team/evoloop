from typing import Any, Dict, List, Optional
from uuid import UUID
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
import asyncio

class EvoLoopCallbackHandler(AsyncCallbackHandler):
    """
    Callback Handler that pushes logs to EvoLoop Link (Server-side Plugin).
    """
    def __init__(self, client: Any, thread_id: str, command_id: Optional[int] = None):
        self.client = client
        self.thread_id = thread_id
        self.command_id = command_id
        self.token_buffer = ""

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        # Notify start of thinking
        self.token_buffer = ""
        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="thought",
            content="Thinking...",
            command_id=self.command_id
        )

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        # User requested to disable streaming. Accumulate silently only if needed for local logic,
        # but here we rely on LLMResult in on_llm_end.
        # Actually, on_llm_end provides the full generation, so we don't need to buffer manually.
        pass

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        if not response.generations:
            return
        
        # Capture the first generation text
        text = response.generations[0][0].text
        if text:
            await self.client.upload_log(
                thread_id=self.thread_id,
                log_type="thought",
                content=text,
                command_id=self.command_id
            )

    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> Any:
        tool_name = serialized.get("name") if serialized else "Unknown Tool"
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
        
        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            content=f"Running {tool_name}...\nInput: {input_str[:200]}",
            command_id=self.command_id
        )

    async def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        # Capture tool output
        content_to_log = output
        
        # Strict sanitation for file reads (including manage_file read)
        is_read_tool = self.current_tool_name in ["read_file", "view_file", "read_file_content"]
        is_manage_read = (self.current_tool_name == "manage_file" and self.current_tool_path)
        
        if (is_read_tool or is_manage_read) and self.current_tool_path:
             lines = output.split('\n')
             count = len(lines)
             if not output: count = 0
             content_to_log = f"File: {self.current_tool_path} (Lines: {count})"
        
        # 1. Truncate for other large outputs (e.g. search results, huge diffs)
        # If the output is huge, we assume it's file content.
        elif len(output) > 500:
             lines = output.split('\n')
             if len(lines) > 20:
                 content_to_log = f"{output[:300]}\n...\n[Truncated {len(lines)} lines / {len(output)} chars]"
                 
        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            content=content_to_log,
            command_id=self.command_id
        )

    async def on_chain_error(self, error: BaseException, **kwargs: Any) -> Any:
        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="error",
            content=str(error),
            command_id=self.command_id
        )
