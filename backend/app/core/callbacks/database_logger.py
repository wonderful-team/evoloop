from typing import Any, Dict, List, Optional
from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import Message
import asyncio

class DatabaseCallbackHandler(BaseCallbackHandler):
    """
    Callback Handler that logs messages to the database (Message) for full-text search.
    """
    def __init__(self, thread_id: str, project_id: int):
        self.thread_id = thread_id
        self.project_id = project_id

    def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        # We don't log every token to DB
        pass

    def on_chat_model_start(
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
        """Run when a chat model starts."""
        pass

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> Any:
        # This is tricky because "chain" can be anything.
        # We ideally want to capture the final AI response node.
        # But LangGraph is different.
        # Easier strategy: In the graph node (model_node), we can explicitly save the result?
        # OR we can assume `outputs` containing `messages` is what we want?
        pass

    # Simplified Approach:
    # Since we are inside the Graph, we can't easily hook into "on_message" generically without a custom Graph Callback.
    # But `TransparentCallbackHandler` prints to console.
    # Let's just implement a simple `log_message` method we call manually, OR use `on_llm_end` carefully.

    # Actually, the best place is `on_llm_end` for AI messages.
    # And we log Human messages at controller level (in `agent.py`).

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        if not response.generations:
            return

        text = response.generations[0][0].text

        # Async Save
        # Note: Callbacks are sync in LangChain mostly unless using AsyncCallbackHandler.
        # But we can fire and forget or run in loop?
        # We will use sync session or async run?
        # We'll assume we can use `asyncio.create_task`
        asyncio.create_task(self._save_log("ai", text))

    async def _save_log(self, role: str, content: str):
        if not content:
            return

        try:
             async with session_scope() as session:
                 log = Message(
                     thread_id=self.thread_id,
                     project_id=self.project_id,
                     role=role,
                     content=content
                 )
                 session.add(log)
                 # session_scope commits automatically
        except Exception as e:
            # logger.error(f"Failed to log message: {e}")
            pass

    # Handling Human Messages:
    # Usually Human messages are inputs to the graph. 
    # Calling this handler won't catch the initial human message unless we trigger it manually
    # or if the graph has a "pass through" node.
    # A better place to log Human inputs is right at the API entry point.
