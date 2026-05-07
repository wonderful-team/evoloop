
import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# --- Standalone Database Setup for Testing ---
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Mock Infrastructure
@patch("app.infrastructure.database.sql.database.db_resource_manager")
@patch("app.core.evocloud.evocloud_manager")
async def run_standalone_test(mock_cloud, mock_db):
    # Setup Mocks
    mock_db.session_factory = TestingSessionLocal
    
    # Import inside because of the mocks
    from app.infrastructure.database.sql.database import Base
    from app.models import Conversation, Message
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import LLMResult, ChatGeneration
    from app.core.engine.callbacks.transparent import TransparentCallbackHandler
    from app.core.engine.callbacks.database_logger import DatabaseCallbackHandler
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.message.thinking import ThinkingProcessor
    from app.infrastructure.database.sql.database import session_scope

    # Initialize Database Schema
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    thread_id = "test-standalone-thread"
    
    # Pre-create conversation
    async with TestingSessionLocal() as session:
        conv = Conversation(id=thread_id, project_id=1, title="Test")
        session.add(conv)
        msg = Message(id=100, thread_id=thread_id, project_id=1, role="human", content="Original prompt", sequence_number=1)
        session.add(msg)
        await session.commit()

    # --- 1. DISPATCH PHASE ---
    with patch("app.infrastructure.config.service.SystemConfigService.get_value", return_value="kimi-k2-thinking-turbo"):
        dispatch_result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content="Retry original prompt",
            is_retry=True,
            skip_message_persistence=True
        )
    
    assert dispatch_result.status == "queued"
    print("✅ Dispatch Phase: OK")

    # --- 2. STREAMING PHASE ---
    trans_callback = TransparentCallbackHandler(thread_id=thread_id)
    trans_callback.monitor = MagicMock()
    trans_callback.monitor.check_cancellation = AsyncMock()
    trans_callback.active_llm_run_id = "retry-run"
    trans_callback.llm_task_id = "task-1"
    
    # Mock Event Bus for streaming
    with patch("app.core.engine.message.event_bus.get_event_bus") as mock_bus:
        bus = MagicMock()
        bus.publish = AsyncMock()
        mock_bus.return_value = bus
        
        # Simulate LLM sending thinking tokens (Kimi style)
        await trans_callback.on_llm_new_token(
            token={"thought": "Processing retry..."}, 
            run_id="retry-run"
        )
        await trans_callback.on_llm_new_token(
            token={"text": "Answer from retry."}, 
            run_id="retry-run"
        )

    # --- 3. PERSISTENCE PHASE ---
    final_msg = AIMessage(content="Answer from retry.")
    result = LLMResult(generations=[[ChatGeneration(text=final_msg.content, message=final_msg)]])
    
    await trans_callback.on_llm_end(result, run_id="retry-run")
    assert final_msg.additional_kwargs.get("thinking") == "Processing retry..."
    print("✅ Streaming & Injection Phase: OK")

    with patch("app.core.engine.callbacks.database_logger.MessageHandler") as mock_handler_class:
        mock_handler = MagicMock()
        mock_handler.handle_ai_message = AsyncMock(return_value={"id": 101, "persisted": True})
        mock_handler_class.return_value = mock_handler
        
        db_callback = DatabaseCallbackHandler(thread_id=thread_id, project_id=1)
        db_callback._handler = mock_handler
        
        await db_callback.on_llm_end(result)
        
        mock_handler.handle_ai_message.assert_called_once()
        args, kwargs = mock_handler.handle_ai_message.call_args
        
        assert kwargs["thinking"] == "Processing retry..."
        assert kwargs["content"] == "Answer from retry."
        print("✅ Persistence Phase: OK (Thinking verified!)")

    print("\n🏆 INTEGRATION TEST PASSED: RETRY LOGIC RECOVERY PROVED.")

if __name__ == "__main__":
    asyncio.run(run_standalone_test())
