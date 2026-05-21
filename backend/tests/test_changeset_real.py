import asyncio
import json
import logging
import os
import sys
import uuid
from unittest.mock import patch

# 环境准备
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.infrastructure.database.sql.database import session_scope
from app.core.engine.message.mapper import BlockMapper
from app.models import Message

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RealChangesetAudit")

async def initialize_system():
    await db_resource_manager.initialize(create_tables=True)
    await MemoryLifespanManager.ainitialize()
    
    from app.infrastructure.database.vector import get_vector_store
    patcher = patch.object(VectorMemoryIndex, "search", return_value=[])
    patcher.start()
    
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)

async def run_targeted_audit():
    await initialize_system()
    
    unique_id = uuid.uuid4().hex[:8]
    prompt = f"请帮我修改本地的 README.md 文件，在末尾加一行唯一标识码：{unique_id}。"
    # Enable Huey immediate mode for synchronous task execution in tests
    from app.infrastructure.queue.factory import get_scheduler
    from app.infrastructure.queue.huey_queue import HueyTaskScheduler
    scheduler = get_scheduler()
    if isinstance(scheduler, HueyTaskScheduler):
        scheduler.get_huey().immediate = True
        print("[TEST] Huey immediate mode ENABLED")

    # 1. 创建测试 Thread
    thread_id = f"targeted-changeset-{uuid.uuid4().hex[:8]}"
    
    logger.info(f"Targeted Prompt: {prompt}")
    
    res = await dispatch_agent_run(thread_id=thread_id, message_content=prompt, project_id=0)
    await run_agent_background(thread_id, res.inputs)
    
    async with session_scope() as session:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        stmt = select(Message).where(Message.thread_id == thread_id).options(selectinload(Message.references))
        db_res = await session.execute(stmt)
        msgs = db_res.scalars().all()
        
        found_changeset = False
        for m in msgs:
            block = BlockMapper.from_db(m)
            if block.has_file_operations:
                found_changeset = True
                logger.info(f"✅ Found Changeset in Msg {m.sequence_number} ({m.role})")
                logger.info(f"   Changeset Count: {block.changeset_count}")
                logger.info(f"   Files: {block.changeset_files}")
        
        if not found_changeset:
            logger.error("❌ Changeset reference NOT found in thread!")

    await db_resource_manager.shutdown()

if __name__ == "__main__":
    asyncio.run(run_targeted_audit())
