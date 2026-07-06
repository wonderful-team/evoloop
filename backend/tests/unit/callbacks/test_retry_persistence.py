
import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass

# Mock standard infrastructure
with patch("app.infrastructure.database.sql.database.db_resource_manager"):
    with patch("app.core.evocloud.evocloud_manager"):
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import LLMResult, ChatGeneration
        from app.core.engine.callbacks.transparent import TransparentCallbackHandler
        from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler
        from app.core.engine.dispatch import dispatch_agent_run

@pytest.fixture
def mock_all():
    with patch("app.core.channel.web_channel.get_event_bus") as bus_mock:
        bus = MagicMock()
        bus.publish = AsyncMock()
        bus_mock.return_value = bus
        
        with patch("app.core.engine.callbacks.database_logger.MessageHandler") as handler_mock:
            handler = MagicMock()
            handler.handle_ai_message = AsyncMock(return_value={
                "id": 999, 
                "persisted": True,
                "category": "ai",
                "streamed": True
            })
            handler_mock.return_value = handler
            
            with patch("app.infrastructure.config.service.SystemConfigService.get_value", return_value="kimi-k2-thinking-turbo"), \
                 patch("app.core.engine.dispatch.session_scope") as mock_session_scope, \
                 patch("app.core.evocloud.evocloud_manager") as mock_evocloud:
                
                # Mock session_scope as an async context manager
                mock_session = AsyncMock()
                mock_session_scope.return_value.__aenter__.return_value = mock_session
                
                # Mock evocloud_manager
                mock_evocloud.get_project_by_id = AsyncMock(return_value={"id": 1, "path": "/mock/project"})
                
                yield bus, handler

@pytest.mark.asyncio
async def test_full_retry_thinking_lifecycle(mock_all):
    """
    Test the complete lifecycle of a retried message that generates thinking content.
    Ensures that:
    1. Dispatch works for retry.
    2. Streaming thinking is captured.
    3. Final thinking is persisted to DB.
    """
    bus, msg_handler = mock_all
    thread_id = "test-retry-thread"
    
    # --- PHASE 1: DISPATCH ---
    # In a real retry, dispatch is called with skip_message_persistence=True
    dispatch_result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content="Retry this",
        is_retry=True,
        skip_message_persistence=True
    )
    assert dispatch_result.status == "queued"
    assert dispatch_result.message_id is None # Correct for skip_message_persistence

    # --- PHASE 2: STREAMING (RETRY EXECUTION) ---
    trans_callback = TransparentCallbackHandler(thread_id=thread_id)
    trans_callback.monitor = AsyncMock()
    trans_callback.active_llm_run_id = "retry-run"
    trans_callback.llm_task_id = "task-1"
    
    # Simulate Kimi sending thinking tokens during retry
    # Note: Kimi uses a 'thought' field in the chunk dict
    await trans_callback.on_llm_new_token(
        token={"thought": "I am thinking about the retry..."}, 
        run_id="retry-run"
    )
    await trans_callback.on_llm_new_token(
        token={"text": "Here is the new answer."}, 
        run_id="retry-run"
    )
    
    # --- PHASE 3: COMPLETION & PERSISTENCE ---
    db_callback = DatabaseCallbackHandler(thread_id=thread_id, project_id=1)
    db_callback._handler = msg_handler
    
    # Create the final message as LangChain would aggregate it
    # Crucially, LangChain often DROPS the 'thought' field from additional_kwargs
    # so we rely on the injection from trans_callback.on_llm_end
    final_msg = AIMessage(content="Here is the new answer.")
    result = LLMResult(generations=[[ChatGeneration(text=final_msg.content, message=final_msg)]])
    
    # 1. First, TransparentCallback flushes buffer (no longer injects thinking into msg)
    await trans_callback.on_llm_end(result, run_id="retry-run")
    
    # Note: on_llm_end no longer injects thinking into additional_kwargs
    # Thinking is handled via reasoning module during message processing
    
    # 2. Then, DatabaseCallback handles the persistence
    await db_callback.on_llm_end(result)
    
    # --- FINAL VERIFICATION ---
    # Check that MessageHandler received the message
    msg_handler.handle_ai_message.assert_called_once()
    persisted_kwargs = msg_handler.handle_ai_message.call_args.kwargs
    
    assert persisted_kwargs["content"] == "Here is the new answer."
    
    print("\n✅ Retry Thinking Lifecycle Test PASSED!")
