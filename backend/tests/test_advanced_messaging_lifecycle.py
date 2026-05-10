import asyncio
import uuid
import os
import json
import logging
from unittest.mock import patch, PropertyMock, AsyncMock

# --- System Setup ---
os.environ["EMBEDDED_MODE"] = "true"
os.environ["APP_ENV"] = "test"

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph, get_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.core.engine.message.repository import MessageRepository
from app.core.engine.hitl import HITLOrchestrator
from app.core.engine.rewind import RewindOrchestrator
from app.core.engine.message.event_bus import get_event_bus
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.models import Message, Conversation
from sqlalchemy import select
from app.infrastructure.database.sql.database import session_scope

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AdvancedMessagingTest")

async def initialize_system():
    logger.info("--- Initializing Advanced Messaging Test System ---")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)
    return graph

async def audit_thread(thread_id: str):
    """Deep audit of message lineage and sequence."""
    async with session_scope() as session:
        stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
        res = await session.execute(stmt)
        msgs = res.scalars().all()
        
        print(f"\n[AUDIT] Thread {thread_id}: {len(msgs)} messages")
        for i, m in enumerate(msgs):
            # 1. Verify UUID format
            try:
                uuid.UUID(m.id)
            except ValueError:
                raise AssertionError(f"Message {m.id} is not a valid UUID")
            
            # 2. Verify Parent Linkage
            if i == 0:
                assert m.parent_id is None, f"First message should have no parent, got {m.parent_id}"
            else:
                assert m.parent_id is not None, f"Message {m.id} (seq {m.sequence_number}) has no parent!"
                # Check if parent exists
                parent_exists = any(str(p.id) == str(m.parent_id) for p in msgs)
                assert parent_exists, f"Parent {m.parent_id} of message {m.id} not found in history!"

            print(f"   [{m.sequence_number}] {m.role.upper()} ID: {m.id[:8]}... Parent: {str(m.parent_id)[:8] if m.parent_id else 'None'}")
    return msgs

async def run_advanced_test():
    graph = await initialize_system()
    project_id = 1
    thread_id = f"adv-test-{uuid.uuid4().hex[:6]}"
    
    # Mocks for EvoCloud
    TOKEN = "dummy-token"
    mock_project = {"id": project_id, "name": "Test Project", "path": os.getcwd()}

    with patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN), \
         patch("app.core.evocloud.evocloud_manager.get_project_by_id", return_value=mock_project):

        # --- PHASE 1: Normal Multi-Turn ---
        print("\n>>> PHASE 1: Normal Multi-Turn")
        turns = ["Hello, what is this project?", "List files in the root directory."]
        for content in turns:
            res = await dispatch_agent_run(thread_id=thread_id, message_content=content, project_id=project_id)
            await run_agent_background(thread_id, res.inputs)
        
        history = await audit_thread(thread_id)
        last_msg_before_rewind = history[-1]

        # --- PHASE 2: Rewind ---
        print("\n>>> PHASE 2: Rewind to turn 1")
        # Find the first AI response ID
        target_msg_id = None
        for m in history:
            if m.role == "ai":
                target_msg_id = m.id
                break
        
        rewind_orchestrator = RewindOrchestrator(event_bus=AsyncMock())
        rewind_res = await rewind_orchestrator.perform_rewind(
            thread_id=thread_id,
            target_message_id=target_msg_id,
            include_target=True, # Remove Turn 1 AI response and everything after
            reason="test_rewind"
        )
        print(f"   - Rewound {rewind_res.removed_message_count} messages.")
        
        # Verify history after rewind
        history_post_rewind = await audit_thread(thread_id)
        assert len(history_post_rewind) < len(history)
        print(f"   - Post-rewind message count: {len(history_post_rewind)}")

        # --- PHASE 3: Branching (New continuity after rewind) ---
        print("\n>>> PHASE 3: Branching from Rewound state")
        res = await dispatch_agent_run(thread_id=thread_id, message_content="Instead of files, tell me about the architecture.", project_id=project_id)
        await run_agent_background(thread_id, res.inputs)
        
        history_branched = await audit_thread(thread_id)
        # Find the human message that was sent after rewind (it should be the second message in history if we rewound to turn 1)
        branched_human = None
        for m in history_branched:
            if m.role == "human" and m.sequence_number > 1:
                branched_human = m
                break
        
        assert branched_human is not None, "Could not find the branched human message"
        assert str(branched_human.parent_id) == str(history_branched[0].id)
        print(f"   - Branching Verification: OK (Message {branched_human.sequence_number} parent is {branched_human.parent_id[:8]})")

        # --- PHASE 4: HITL Simulation ---
        print("\n>>> PHASE 4: HITL Simulation")
        # We simulate a state where a tool is pending
        mock_tool_call = {
            "id": f"call_{uuid.uuid4().hex[:4]}",
            "name": "read_file",
            "args": {"path": "pyproject.toml"}
        }
        
        # Manually persist a message with tool_calls to simulate graph interruption
        repo = MessageRepository(thread_id=thread_id, project_id=project_id)
        # In real system, HITL request is a system message with the tool_call_id
        ai_msg_id, _ = await repo.persist(
            role="system",
            content="I need to read the file. Please confirm.",
            tool_calls=[mock_tool_call],
            tool_call_id=mock_tool_call["id"],
            status="pending"
        )
        print(f"   - Simulated HITL Pending Message: {ai_msg_id[:8]}")
        
        # Verify it shows up in history as pending
        async with session_scope() as session:
            m = (await session.execute(select(Message).where(Message.id == ai_msg_id))).scalar_one()
            assert m.status == "pending"
        
        # Handle Resume via HITLOrchestrator
        print("   - Resolving HITL via Orchestrator...")
        normalized = await HITLOrchestrator.handle_resume(
            thread_id=thread_id,
            tool_call=mock_tool_call,
            user_input="Approved"
        )
        assert normalized == "Approved"
        
        # Verify status is now completed
        async with session_scope() as session:
            m = (await session.execute(select(Message).where(Message.id == ai_msg_id))).scalar_one()
            assert m.status == "completed"
            print("   - HITL Status Closure Verification: OK")

    print("\n✅ ADVANCED MESSAGING LIFECYCLE TEST PASSED!")

if __name__ == "__main__":
    try:
        asyncio.run(run_advanced_test())
    finally:
        # Cleanup
        if os.path.exists("test_evoloop.db"):
             # os.remove("test_evoloop.db")
             pass
