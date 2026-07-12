import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock

from dotenv import load_dotenv
load_dotenv()

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database import session_scope
from sqlalchemy import select
from app.models import Message, MessageReference, FileOperation, HumanRequest
from app.core.engine.message.broker import get_message_broker
from app.api.routes.conversations._messages import get_conversation_messages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("comprehensive_audit")

class MockEventBus:
    def __init__(self):
        self.events = []
    async def publish(self, channel, data):
        self.events.append({"channel": channel, "data": json.loads(data)})
    async def subscribe(self, channel): pass
    async def unsubscribe(self, channel): pass

async def initialize_system():
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    from app.core.memory.lifespan import MemoryLifespanManager
    await MemoryLifespanManager.ainitialize()
    from app.core.events.discovery import auto_discover_handlers
    auto_discover_handlers()
    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)

async def run_comprehensive_audit():
    await initialize_system()
    
    thread_id = f"audit-{uuid.uuid4().hex[:6]}"
    project_id = 0
    settings.EMBEDDED_MODE = True
    settings.LANCEDB_PATH = f"/tmp/lancedb_audit_{uuid.uuid4().hex[:6]}" # Temporary path for clean state
    settings.EMBEDDING_DIMENSIONS = 384
    settings.AUTO_MEMORY_EXTRACTION = False
    
    mock_bus = MockEventBus()
    
    logger.info(f"--- Starting Comprehensive Audit for Thread: {thread_id} ---")
    
    # Aggressively mock LanceDB to avoid any dimension mismatch
    mock_lancedb = MagicMock()
    mock_table = MagicMock()
    mock_table.search = MagicMock(return_value=MagicMock(to_batches=MagicMock(return_value=[])))
    mock_lancedb.open_table = MagicMock(return_value=mock_table)
    mock_lancedb.create_table = MagicMock(return_value=mock_table)
    
    with patch("app.core.engine.message.publisher.get_message_broker", return_value=mock_bus), \
         patch("lancedb.connect", return_value=mock_lancedb):
        # Turn 1: Generate artifacts and files
        prompt = (
            "Create a file 'audit.txt' with 'Audit Log'. "
            "Then show a pie chart using ```echarts. "
            "Finally, use ![Audit Screenshot](file:///uploads/audit.png) in your text."
        )
        
        logger.info("Executing Turn 1...")
        dispatch_res = await dispatch_agent_run(thread_id=thread_id, message_content=prompt, project_id=project_id)
        await run_agent_background(thread_id, dispatch_res.inputs)
        
        # Turn 2: Trigger HITL
        logger.info("Executing Turn 2 (HITL)...")
        hitl_prompt = "Ask me for approval before deleting audit.txt."
        dispatch_res = await dispatch_agent_run(thread_id=thread_id, message_content=hitl_prompt, project_id=project_id)
        try:
            await run_agent_background(thread_id, dispatch_res.inputs)
        except Exception:
            logger.info("Agent interrupted for HITL as expected.")

    # --- VERIFICATION ---
    logger.info("\n" + "="*50)
    logger.info("AUDIT VERIFICATION REPORT")
    logger.info("="*50)
    
    # 1. SSE Verification
    logger.info("\n[1] Checking SSE Events...")
    ai_events = [e for e in mock_bus.events if e["data"].get("data", {}).get("role") == "ai" and e["data"].get("data", {}).get("status") == "completed"]
    
    if ai_events:
        last_ai_event = ai_events[0]["data"]["data"]
        refs = last_ai_event.get("references", [])
        logger.info(f"Detected {len(refs)} references in completed SSE event.")
        for r in refs:
            logger.info(f" ✅ SSE Reference: {r['type']} - {r['target_name']}")
    else:
        logger.error(" ❌ No completed AI SSE events captured!")

    # 2. History API Verification
    logger.info("\n[2] Checking History API (get_conversation_messages)...")
    history_res = await get_conversation_messages(thread_id=thread_id)
    history_msgs = history_res.data
    
    found_types = set()
    for msg in history_msgs:
        found_types.add(msg.role)
        if msg.references:
            for r in msg.references:
                found_types.add(f"ref:{r.type}")
    
    expected_roles = {"human", "ai", "tool", "system"}
    for role in expected_roles:
        status = "✅" if role in found_types else "❌"
        logger.info(f" {status} Role: {role}")
        
    expected_refs = {"ref:file", "ref:artifact", "ref:image"}
    for ref in expected_refs:
        status = "✅" if ref in found_types else "❌"
        logger.info(f" {status} Reference: {ref}")

    # 3. DB Integrity Check
    logger.info("\n[3] Checking Database Records...")
    async with session_scope() as session:
        stmt = select(Message).where(Message.thread_id == thread_id)
        res = await session.execute(stmt)
        messages = res.scalars().all()
        logger.info(f"Total messages in DB: {len(messages)}")
        
        # Check HITL
        stmt_hr = select(HumanRequest).where(HumanRequest.thread_id == thread_id)
        res_hr = await session.execute(stmt_hr)
        hits = res_hr.scalars().all()
        if hits:
            logger.info(f" ✅ HITL Request Found: {hits[0].type} - {hits[0].status}")
        else:
            logger.error(" ❌ No HITL request found in DB!")

    logger.info("\nAudit Complete.")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_audit())
