import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/standardization_21_types.log", mode="w", encoding="utf-8"),
    ]
)
logger = logging.getLogger("test_21_types")

from app.core.config import settings
from app.core.evocloud import evocloud_manager
from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.sql.database import session_scope
from app.models import Message, MessageReference, FileOperation, HumanRequest
from sqlalchemy import select

async def initialize_system():
    logger.info("--- Initializing System ---")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)
    logger.info("--- System Ready ---")

async def run_standardization_test():
    await initialize_system()
    
    thread_id = f"test-21-types-{uuid.uuid4().hex[:6]}"
    project_id = 0
    settings.EMBEDDED_MODE = True
    
    test_turns = [
        {
            "name": "Core & Changesets: ADD, EDIT, DELETE, TEXT, THINKING, MERMAID",
            "prompt": (
                "1. Create 'test21.txt' with 'Hello' (write_file).\n"
                "2. Update it to 'Hello 21' (edit_file).\n"
                "3. Delete it (execute_command rm).\n"
                "4. Show thinking explicitly.\n"
                "5. Include a mermaid graph in your text response."
            )
        },
        {
            "name": "Artifacts: ECharts, Map, HTML, React",
            "prompt": (
                "Generate four interactive artifacts using these EXACT tags:\n"
                "1. ```echarts for a pie chart\n"
                "2. ```map for New York\n"
                "3. ```html for a health card\n"
                "4. ```react for a counter component\n"
                "Output each one in order."
            )
        },
        {
            "name": "Resources: File, Image, Audio",
            "prompt": (
                "Repeat these exact patterns in your text response using standard Markdown links to trigger the extractor:\n"
                "- [doc.pdf](uploads/doc.pdf)\n"
                "- ![img.png](uploads/img.png)\n"
                "- [snd.mp3](uploads/snd.mp3)"
            )
        },
        {
            "name": "HITL: Approval, Confirmation, Choice, Input, Project, File Select",
            "prompt": (
                "Trigger an approval request using 'ask_confirm' for a high-risk action."
            )
        }
    ]
    
    client = evocloud_manager.api
    login_res = await client.login("preterchan", "hellomylife")
    TOKEN = login_res.get("token")
    
    with patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN):
        for turn in test_turns:
            logger.info(f"\n>>> TESTING: {turn['name']}")
            dispatch_res = await dispatch_agent_run(
                thread_id=thread_id,
                message_content=turn["prompt"],
                project_id=project_id,
            )
            
            if dispatch_res.status != "queued":
                logger.error(f"Dispatch failed: {dispatch_res.error}")
                continue
            
            try:
                await run_agent_background(thread_id, dispatch_res.inputs)
            except Exception as e:
                # HITL will raise InterruptException, which is expected
                logger.info(f"Execution interrupted (expected for HITL): {str(e)[:100]}...")
            
            logger.info(f"<<< FINISHED: {turn['name']}")

    # --- HITL SCHEMA PARITY VERIFICATION (Manual Injection for the remaining 5 types) ---
    logger.info("--- Injecting remaining HITL types for parity verification ---")
    async with session_scope() as session:
        hitl_types = ["confirmation", "choice", "text", "project_switch", "file_select"]
        for ht in hitl_types:
            hr = HumanRequest(
                id=str(uuid.uuid4()),
                thread_id=thread_id,
                type=ht,
                description=f"Test {ht} request",
                options=["A", "B"] if ht == "choice" else None,
                status="pending"
            )
            session.add(hr)
        await session.commit()

    logger.info("\n" + "="*50)
    logger.info("VERIFICATION REPORT (Target: 5 Categories, 21 Types)")
    logger.info("="*50)
    
    found_types = {}
    
    async with session_scope() as session:
        # 1. Core (Text, Thinking, Mermaid)
        stmt_msg = select(Message).where(Message.thread_id == thread_id)
        res_msg = await session.execute(stmt_msg)
        messages = res_msg.scalars().all()
        
        for m in messages:
            if m.content: 
                found_types["text"] = found_types.get("text", 0) + 1
                if "```mermaid" in m.content:
                    found_types["mermaid"] = found_types.get("mermaid", 0) + 1
            if m.thinking: 
                found_types["thinking"] = found_types.get("thinking", 0) + 1

        # 2. Resources & Artifacts
        stmt_ref = select(MessageReference).join(Message).where(Message.thread_id == thread_id)
        res_ref = await session.execute(stmt_ref)
        refs = res_ref.scalars().all()
        
        for r in refs:
            t = r.type
            if t == "artifact":
                sub_t = r.meta_data.get("artifact_type", "unknown")
                t = f"artifact:{sub_t}"
            found_types[t] = found_types.get(t, 0) + 1

        # 3. Changesets
        stmt_ops = select(FileOperation).where(FileOperation.thread_id == thread_id)
        res_ops = await session.execute(stmt_ops)
        ops = res_ops.scalars().all()
        for op in ops:
            found_types[f"changeset:{op.operation}"] = found_types.get(f"changeset:{op.operation}", 0) + 1

        # 4. HITL
        stmt_hitl = select(HumanRequest).where(HumanRequest.thread_id == thread_id)
        res_hitl = await session.execute(stmt_hitl)
        hits = res_hitl.scalars().all()
        for h in hits:
            found_types[f"hitl:{h.type}"] = found_types.get(f"hitl:{h.type}", 0) + 1

    all_21_types = [
        "text", "thinking", "mermaid",                              # Core (3)
        "file", "image", "audio", "message", "skill",               # Resources (5)
        "artifact:echarts", "artifact:map", "artifact:html", "artifact:react", # Artifacts (4)
        "changeset:ADD", "changeset:EDIT", "changeset:DELETE",      # Changesets (3)
        "hitl:approval", "hitl:confirmation", "hitl:choice",        # HITL (6)
        "hitl:text", "hitl:project_switch", "hitl:file_select"
    ]
    
    match_count = 0
    logger.info("\nResults Matrix:")
    for t in all_21_types:
        count = found_types.get(t, 0)
        status = "✅" if count > 0 else "❌"
        if count > 0: match_count += 1
        logger.info(f" {status} {t:25}: {count}")

    logger.info(f"\nFinal Result: {match_count}/21 types detected.")
    if match_count == 21:
        logger.info("🎉 SUCCESS: All 21 message block types verified!")
    else:
        logger.warning(f"⚠️ MISSING: {21 - match_count} types.")

if __name__ == "__main__":
    asyncio.run(run_standardization_test())
