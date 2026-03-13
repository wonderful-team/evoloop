
import asyncio
import time
import os
import sys

# Setup paths
PROJECT_ROOT = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend"
sys.path.append(PROJECT_ROOT)

from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.sql.database import session_scope
from app.models.conversation import Message
from sqlalchemy import select, func

async def verify_persistence():
    # --- Minimal Initialization ---
    from app.core.globals import set_graph
    from app.core.persistence import set_checkpointer, set_db_pool
    from app.core.engine.graph_builder import GraphBuilder
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool
    from app.core.config import settings
    from app.initial_data import init as init_data
    from app.core.memory import memory_manager

    # 1. Init Data (Settings)
    await asyncio.to_thread(init_data)
    try:
        await memory_manager.initialize()
    except Exception:
        pass # Already initialized likely

    # 2. Persistence
    db_uri = settings.CHECKPOINTER_DATABASE_URI
    db_pool = AsyncConnectionPool(conninfo=db_uri, max_size=5, kwargs={"autocommit": True}, open=False)
    await db_pool.open()
    checkpointer = AsyncPostgresSaver(db_pool)
    await checkpointer.setup()
    set_db_pool(db_pool)
    set_checkpointer(checkpointer)

    # 3. Graph
    builder = GraphBuilder()
    config_path = os.path.join(PROJECT_ROOT, "app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)

    thread_id = f"test-persistence-{int(time.time())}"
    print(f"Starting verification for thread: {thread_id}")
    
    # Inputs that will lead to supervisor -> finish
    inputs = {
        "messages": [{"role": "human", "content": "任务已完成，请生成总结并结束。"}],
        "project_id": 1,
        "task_title": "Persistence Test"
    }

    # Start the agent background task
    start_time = time.time()
    await run_agent_background(thread_id, inputs)
    end_time = time.time()
    
    duration = end_time - start_time
    print(f"Agent execution completed in {duration:.2f} seconds.")
    
    # Check DB for the final message
    async with session_scope() as session:
        stmt = (
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.id.desc())
        )
        result = await session.execute(stmt)
        messages = result.scalars().all()
        
        found_summary = False
        for msg in messages:
            print(f"Found message: ID={msg.id}, Role={msg.role}, Seq={msg.sequence_number}, Content={str(msg.content)[:50]}...")
            if msg.role == "ai" and ("任务完成" in str(msg.content) or "Perfect" in str(msg.content) or "总结" in str(msg.content)):
                found_summary = True
        
        if found_summary:
            print(f"SUCCESS: Final summary message found in DB immediately after run!")
        else:
            print("FAILED: Final summary message NOT found in DB. Race condition might still exist or node flow differed.")

    await db_pool.close()

if __name__ == "__main__":
    asyncio.run(verify_persistence())
