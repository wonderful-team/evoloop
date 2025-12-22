from typing import Any, Dict, List, Optional
from uuid import UUID
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
import asyncio
from app.infrastructure.evoloop_link.client import EvoLoopLinkClient

class EvoLoopCallbackHandler(AsyncCallbackHandler):
    """
    Callback Handler that pushes logs to EvoLoop Link (Server-side Plugin).
    """
    def __init__(self, client: EvoLoopLinkClient, thread_id: str, command_id: Optional[int] = None):
        self.client = client
        self.thread_id = thread_id
        self.command_id = command_id

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        pass

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        if not response.generations:
            return
        
        # Capture the first generation text as "thought"
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
        pass

    async def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        # Capture tool output
        # serialized = kwargs.get("serialized", {})
        # name = serialized.get("name", "tool")
        
        # We can try to get the tool name from the run manager or kwargs if available, 
        # but LangChain v0.1+ might differ.
        # For now, just logging the output is useful.
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
