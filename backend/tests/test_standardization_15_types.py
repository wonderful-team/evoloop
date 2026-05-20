import asyncio
import json
import logging
import os
import sys
import uuid
import shutil
from pathlib import Path
from unittest.mock import patch, PropertyMock

from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/standardization_15_types.log", mode="w", encoding="utf-8"),
    ]
)
logger = logging.getLogger("test_15_types")

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
from app.models import Message, MessageReference, FileOperation
from sqlalchemy import select, desc

async def initialize_system():
    logger.info("--- Initializing System ---")
    # Use existing DB but ensuring tables are updated if necessary
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)
    logger.info("--- System Ready ---")

async def run_targeted_test():
    await initialize_system()
    
    thread_id = f"test-15-types-{uuid.uuid4().hex[:6]}"
    project_id = 0
    
    settings.EMBEDDED_MODE = True  # Enable embedded mode for synchronous background tasks (important for changesets)
    logger.info(f"--- Settings: EMBEDDED_MODE={settings.EMBEDDED_MODE} ---")

    # We will run a few turns to trigger all types
    test_turns = [
        {
            "name": "Changesets & Thinking: ADD, EDIT, DELETE, THINKING",
            "prompt": (
                "Let's start with file operations. You MUST use your file tools (write_file, edit_file) and NOT execute_command for these steps:\n"
                "1. Create a file 'std_test.txt' with 'Initial content' using write_file.\n"
                "2. Update 'std_test.txt' to 'Standardized content' using edit_file (replace 'Initial content' with 'Standardized content').\n"
                "3. Delete 'std_test.txt' using execute_command('rm std_test.txt').\n"
                "Also, please show your internal thinking process explicitly in a <thinking> block."
            )
        },
        {
            "name": "Artifacts: ECharts, Mermaid, Map, HTML, React",
            "prompt": (
                "Show me your visualization and UI skills. Please generate ALL of these in separate blocks:\n"
                "1. An ECharts pie chart (```echarts).\n"
                "2. A Mermaid flowchart (```mermaid).\n"
                "3. A Map block for 'Silicon Valley' (```map).\n"
                "4. A beautiful HTML snippet (```html).\n"
                "5. A React component snippet (```react)."
            )
        },
        {
            "name": "Resources: File, Image, Audio, Message, Skill",
            "prompt": (
                "Please explicitly mention these resource references in your response text to trigger the extractor:\n"
                "1. Path: uploads/sample.pdf\n"
                "2. Path: uploads/photo.jpg\n"
                "3. Path: uploads/voice.mp3\n"
                "4. Message ID: @[message:00000000-0000-0000-0000-000000000000]\n"
                "5. Skill ID: @[skill:skill_test_123]"
            )
        }
    ]
    
    # Login to get token for dispatch
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
            
            await run_agent_background(thread_id, dispatch_res.inputs)
            logger.info(f"<<< FINISHED: {turn['name']}")

    # Wait for background tasks
    logger.info("Waiting 5 seconds for background tasks...")
    await asyncio.sleep(5)

    # --- VERIFICATION PHASE ---
    logger.info("\n" + "="*50)
    logger.info("VERIFICATION REPORT (Target: 4 Categories, 15 Types)")
    logger.info("="*50)
    
    async with session_scope() as session:
        # 0. Check Core Types (Text & Thinking)
        stmt_msg = select(Message).where(Message.thread_id == thread_id)
        res_msg = await session.execute(stmt_msg)
        messages = res_msg.scalars().all()
        
        found_types = {"text": 0, "thinking": 0}
        for m in messages:
            if m.content:
                found_types["text"] += 1
            if m.thinking:
                found_types["thinking"] += 1

        # 1. Check MessageReferences (Resources & Artifacts)
        stmt = select(MessageReference).join(Message).where(Message.thread_id == thread_id)
        res = await session.execute(stmt)
        refs = res.scalars().all()
        
        for r in refs:
            t = r.type
            if t == "artifact":
                sub_t = r.meta_data.get("artifact_type", "unknown")
                t = f"artifact:{sub_t}"
            
            found_types[t] = found_types.get(t, 0) + 1
            logger.info(f"[Found] Reference: Type={t}, Target={r.target_name}")

        # 2. Check FileOperations (Changesets)
        stmt_ops = select(FileOperation).where(FileOperation.thread_id == thread_id)
        res_ops = await session.execute(stmt_ops)
        ops = res_ops.scalars().all()
        for op in ops:
            t = f"changeset:{op.operation}"
            found_types[t] = found_types.get(t, 0) + 1
            logger.info(f"[Found] FileOp: {op.operation} on {op.file_path}")

    logger.info("\nSummary of detected types (Goal is 15):")
    all_standard_types = [
        "text", "thinking",                             # Core (2)
        "file", "image", "audio", "message", "skill",    # Resources (5)
        "artifact:echarts", "artifact:mermaid", "artifact:map", "artifact:html", "artifact:react", # Artifacts (5)
        "changeset:ADD", "changeset:EDIT", "changeset:DELETE" # Changesets (3)
    ]
    
    match_count = 0
    for t in all_standard_types:
        count = found_types.get(t, 0)
        status = "✅" if count > 0 else "❌"
        if count > 0: match_count += 1
        logger.info(f" {status} {t:20}: {count}")

    logger.info(f"\nFinal Result: {match_count}/15 types detected.")
    if match_count == 15:
        logger.info("🎉 SUCCESS: All 15 message block types verified!")
    else:
        logger.warning(f"⚠️ MISSING: {15 - match_count} types not detected.")

if __name__ == "__main__":
    asyncio.run(run_targeted_test())
