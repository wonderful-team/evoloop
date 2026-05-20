import asyncio
import json
import logging
import os
import sys
import uuid
from typing import List

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RealAgentAudit")

from unittest.mock import patch

async def initialize_system():
    logger.info("--- Initializing Real Agent Environment ---")
    await db_resource_manager.initialize(create_tables=True)
    await MemoryLifespanManager.ainitialize()
    
    # Mock 掉向量数据库搜索，防止维度不匹配报错
    from app.core.memory.backends.vector_index import VectorMemoryIndex
    patcher = patch.object(VectorMemoryIndex, "search", return_value=[])
    patcher.start()
    logger.info("[Mock] VectorMemoryIndex.search patched (returns empty list)")
    
    auto_discover_handlers()
    builder = GraphBuilder()
    # 使用标准配置
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)
    logger.info("--- System Ready ---")

async def run_and_audit(prompt: str, thread_id: str, label: str):
    logger.info(f"\n[Scenario: {label}] Prompt: {prompt}")
    
    # 1. Dispatch
    res = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=prompt,
        project_id=0
    )
    
    if res.status != "queued":
        logger.error(f"Dispatch failed: {res.error}")
        return

    # 2. Run Background (Wait for finish)
    logger.info("  Running Agent...")
    await run_agent_background(thread_id, res.inputs)
    
    # 3. Audit Result (Audit ALL messages in thread)
    async with session_scope() as session:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        stmt = select(Message).where(
            Message.thread_id == thread_id
        ).order_by(Message.sequence_number).options(selectinload(Message.references))
        
        db_res = await session.execute(stmt)
        msgs = db_res.scalars().all()
        
        logger.info(f"--- [Audit Report: {label}] ---")
        total_refs = 0
        for m in msgs:
            block = BlockMapper.from_db(m)
            ref_count = len(block.references) if block.references else 0
            total_refs += ref_count
            if ref_count > 0 or m.role == "ai":
                logger.info(f"  Msg {m.sequence_number} ({m.role}, {m.category}): {ref_count} refs")
                if block.references:
                    for r in block.references:
                        logger.info(f"    - [{r.type}] {r.target_name}")
                if block.has_file_operations:
                    logger.info(f"    - [TOP-LEVEL] has_file_operations: True (Count: {block.changeset_count})")
        
        if total_refs == 0:
            logger.warning(f"  ⚠️ No references found in thread {thread_id}")
        else:
            logger.info(f"  ✅ Total references in thread: {total_refs}")

async def main():
    await initialize_system()
    
    test_cases = [
        ("请生成一个包含 5 行随机用户数据的 CSV 文件，保存在 uploads 目录下。", "real-file-test"),
        ("根据数据 [10, 50, 30, 90] 展示一个销售趋势的 ECharts 图表。", "real-artifact-test"),
        ("请帮我修改本地的 README.md 文件，在末尾加一行 'Audit Passed'。", "real-changeset-test")
    ]
    
    for prompt, thread_id_prefix in test_cases:
        thread_id = f"{thread_id_prefix}-{uuid.uuid4().hex[:4]}"
        await run_and_audit(prompt, thread_id, thread_id_prefix)

    await db_resource_manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
