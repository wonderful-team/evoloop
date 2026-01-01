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
        self.token_buffer += token
        # Throttle updates: flush on newline or every 50 chars
        if "\n" in token or len(self.token_buffer) >= 50:
            await self.client.upload_log(
                thread_id=self.thread_id,
                log_type="thought",
                content=self.token_buffer,
                command_id=self.command_id
            )
            self.token_buffer = ""

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        if not response.generations:
            return
        
        # Capture the first generation text
        text = response.generations[0][0].text
        if text:
            # We overwrite or append? The UI renders distinct log items.
            # So this will be a second "thought" item with the actual content.
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
        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            content=f"Running {tool_name}...\nInput: {input_str[:200]}",
            command_id=self.command_id
        )

    async def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        # Capture tool output
        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            content=output,
            command_id=self.command_id
        )

    async def on_chain_error(self, error: BaseException, **kwargs: Any) -> Any:
        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="error",
            content=str(error),
            command_id=self.command_id
        )
