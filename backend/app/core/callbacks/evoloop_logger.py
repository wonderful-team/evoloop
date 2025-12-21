from typing import Any, Dict, List, Optional
from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
import asyncio
from app.infrastructure.evoloop_link.client import EvoLoopLinkClient

class EvoLoopCallbackHandler(BaseCallbackHandler):
    """
    Callback Handler that pushes logs to EvoLoop Link (Server-side Plugin).
    """
    def __init__(self, client: EvoLoopLinkClient, thread_id: str):
        self.client = client
        self.thread_id = thread_id

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        pass

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        if not response.generations:
            return
        
        # Capture the first generation text as "thought"
        text = response.generations[0][0].text
        if text:
            asyncio.create_task(self.client.upload_log(
                thread_id=self.thread_id,
                log_type="thought",
                content=text
            ))

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> Any:
        pass

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        # Capture tool output
        # serialized = kwargs.get("serialized", {})
        # name = serialized.get("name", "tool")
        
        # We can try to get the tool name from the run manager or kwargs if available, 
        # but LangChain v0.1+ might differ.
        # For now, just logging the output is useful.
        asyncio.create_task(self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            content=output
        ))

    def on_chain_error(self, error: BaseException, **kwargs: Any) -> Any:
        asyncio.create_task(self.client.upload_log(
            thread_id=self.thread_id,
            log_type="error",
            content=str(error)
        ))
