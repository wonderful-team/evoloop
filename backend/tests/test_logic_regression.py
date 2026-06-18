import asyncio
import uuid
import os
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

pytestmark = pytest.mark.skip(reason="Integration test - requires full backend with DB initialization")

# Mock Environment
os.environ["EMBEDDED_MODE"] = "true"

from app.core.engine.message.repository import MessageRepository
from app.core.hitl.orchestrator import HITLOrchestrator
from app.core.engine.dispatch import dispatch_agent_run
from app.models import Message

async def test_logic_lifecycle():
    print("\n🚀 Starting PURE LOGIC Full-Lifecycle Regression Test...")
    
    thread_id = str(uuid.uuid4())
    project_id = 1
    
    # --- Step 1: Persistence Logic (via Repository) ---
    print("\n[Step 1] Testing Message Persistence...")
    repo = MessageRepository(thread_id=thread_id, project_id=project_id)
    
    # Persist first human message
    msg1_id, seq1 = await repo.persist(
        role="human",
        content="First logical message"
    )
    print(f"   - Message 1 Persisted (ID: {msg1_id}, Seq: {seq1})")
    
    # Persist second message (AI) - should automatically link to msg1
    msg2_id, seq2 = await repo.persist(
        role="ai",
        content="AI Response"
    )
    print(f"   - Message 2 Persisted (ID: {msg2_id}, Seq: {seq2})")
    
    # Verify Threading
    from app.infrastructure.database.sql.database import session_scope
    async with session_scope() as session:
        from sqlalchemy import select
        m2 = (await session.execute(select(Message).where(Message.id == msg2_id))).scalar_one()
        print(f"   - Message 2 Parent ID: {m2.parent_id}")
        assert str(m2.parent_id) == str(msg1_id), f"Parent ID mismatch! Expected {msg1_id}, got {m2.parent_id}"

    # --- Step 2: HITL Logic (via Orchestrator) ---
    print("\n[Step 2] Testing HITL Orchestration...")
    
    # Mock a pending tool call
    mock_tool_call = {
        "id": "call_123",
        "name": "request_human_input",
        "args": {"prompt": "What is your name?"}
    }
    
    # Mock MessageRepository.update_status_by_tool_call_id
    with patch("app.core.engine.message.repository.MessageRepository.update_status_by_tool_call_id", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = True
        
        # Test handle_resume
        normalized = await HITLOrchestrator.handle_resume(
            thread_id=thread_id,
            tool_call=mock_tool_call,
            user_input="Antigravity"
        )
        print(f"   - HITL Normalized Input: {normalized}")
        assert normalized == "Antigravity"
        mock_update.assert_called_once_with("call_123", "completed")
        print("   - HITL Status Closure: OK")

    # --- Step 3: History Retrieval (New Refactored logic) ---
    print("\n[Step 3] Testing Encapsulated History Retrieval...")
    messages, has_more, total = await repo.get_full_history(limit=10)
    print(f"   - History fetched: {len(messages)} messages, Total: {total}")
    assert len(messages) >= 2
    assert messages[0].id == msg1_id
    assert messages[1].id == msg2_id

    # --- Step 4: Dispatch Logic ---
    print("\n[Step 4] Testing Unified Dispatch...")
    # Mock evocloud_manager and other globals
    with patch("app.core.evocloud.manager.evocloud_manager.sync_message", new_callable=AsyncMock):
        with patch("app.core.monitoring.activity.activity_monitor.update_status", new_callable=AsyncMock):
            result = await dispatch_agent_run(
                thread_id=thread_id,
                message_content="Third message via dispatch",
                project_id=project_id
            )
            print(f"   - Dispatch status: {result.status}")
            assert result.status == "success"
            
            # Verify the new message has parent_id set to AI message
            async with session_scope() as session:
                m3 = (await session.execute(select(Message).where(Message.id == result.message_id))).scalar_one()
                print(f"   - Message 3 Parent ID: {m3.parent_id}")
                assert str(m3.parent_id) == str(msg2_id)

    print("\n✅ PURE LOGIC Full-Lifecycle Regression Test Passed!")

if __name__ == "__main__":
    asyncio.run(test_logic_lifecycle())
