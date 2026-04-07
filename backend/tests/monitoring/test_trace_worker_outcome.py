#!/usr/bin/env python3
"""
追踪 worker_outcome 的设置和读取
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("trace_outcome")

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

env_path = '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

# 修补 Worker 和 Supervisor 来添加追踪日志
original_worker_post_process = None
original_supervisor_call = None

def patch_worker():
    """修补 Worker 的 _post_process_result 方法"""
    from app.core.engine.nodes.worker import WorkerNode
    
    global original_worker_post_process
    original_worker_post_process = WorkerNode._post_process_result
    
    def patched_post_process(self, state, engine_result, execution_ticket, role_name):
        last_msg = engine_result["messages"][-1]
        content = last_msg.content if hasattr(last_msg, 'content') else ""
        
        # 计算 worker_outcome
        if "[ERROR:" in str(content) or str(content).strip().startswith("Error:"):
            worker_outcome = "failed"
        else:
            worker_outcome = "success"
        
        agent_config = execution_ticket.get("agent_config", {})
        is_subtask = agent_config.get("is_subtask", False)
        
        logger.info(f"[WorkerPatch] 计算 worker_outcome: '{worker_outcome}'")
        logger.info(f"[WorkerPatch] is_subtask: {is_subtask}")
        logger.info(f"[WorkerPatch] 将设置 blackboard['worker_outcome'] = '{worker_outcome}'")
        
        # 调用原始方法
        result = original_worker_post_process(self, state, engine_result, execution_ticket, role_name)
        
        # 检查结果
        blackboard = result.get("blackboard", {})
        actual_outcome = blackboard.get("worker_outcome")
        next_node = result.get("next_node")
        logger.info(f"[WorkerPatch] 返回结果: next_node={next_node}, worker_outcome={actual_outcome}")
        
        return result
    
    WorkerNode._post_process_result = patched_post_process
    logger.info("✅ Worker 已修补")


def patch_supervisor():
    """修补 Supervisor 的 __call__ 方法"""
    from app.core.engine.nodes.supervisor import SupervisorNode
    
    global original_supervisor_call
    original_supervisor_call = SupervisorNode.__call__
    
    async def patched_call(self, state, config):
        blackboard = state.get("blackboard") or {}
        worker_outcome = blackboard.get("worker_outcome")
        iteration_count = state.get("iteration_count", 0)
        
        logger.info(f"[SupervisorPatch] 被调用，iteration={iteration_count}")
        logger.info(f"[SupervisorPatch] 读取 worker_outcome: {worker_outcome}")
        
        if worker_outcome:
            logger.info(f"[SupervisorPatch] worker_outcome 存在，值: '{worker_outcome}'")
            if worker_outcome == "success":
                logger.info(f"[SupervisorPatch] ✅ 应该 FINISH!")
            else:
                logger.info(f"[SupervisorPatch] 🔄 需要重新规划")
        else:
            logger.info(f"[SupervisorPatch] worker_outcome 为 None/空，进入 LLM 决策")
        
        # 调用原始方法
        result = await original_supervisor_call(self, state, config)
        
        next_node = result.get("next_node")
        logger.info(f"[SupervisorPatch] 返回结果: next_node={next_node}")
        
        return result
    
    SupervisorNode.__call__ = patched_call
    logger.info("✅ Supervisor 已修补")


async def init():
    from app.infrastructure.database.sql.database import Base, engine
    from sqlmodel import SQLModel
    from app.core.config import settings
    
    if settings.EMBEDDED_MODE:
        from app import models
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)
    
    try:
        from app.initial_data import init as init_data
        await asyncio.to_thread(init_data)
    except:
        pass
    
    # Initialize Memory using MemoryContainer
    try:
        from app.core.memory import MemoryContainer, MemoryConfig
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        # Store container for cleanup
        global _memory_container
        _memory_container = container
        logger.info("✅ Memory Manager 初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ Memory 初始化失败: {e}")
    
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    import aiosqlite
    db_uri = settings.CHECKPOINTER_DATABASE_URI
    sqlite_path = db_uri.replace("sqlite+aiosqlite://", "").replace("sqlite://", "")
    conn = await aiosqlite.connect(sqlite_path)
    checkpointer = AsyncSqliteSaver(conn=conn)
    await checkpointer.setup()
    
    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    from app.core.persistence import set_checkpointer
    
    set_checkpointer(checkpointer)
    builder = GraphBuilder()
    config_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/config/agent_main.yaml"
    graph = builder.build(config_path, checkpointer=checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)
    
    return True


async def test():
    # 先修补
    patch_worker()
    patch_supervisor()
    
    await init()
    
    from app.core.engine.background_agent import run_agent_background
    
    thread_id = f"trace-outcome-{datetime.now().strftime('%H%M%S')}"
    user_input = "帮我写一个 Python 函数，计算斐波那契数列"
    
    logger.info("="*70)
    logger.info(f"🕵️ 追踪 worker_outcome")
    logger.info(f"Thread: {thread_id}")
    logger.info("="*70)
    
    inputs = {
        "messages": [{"type": "human", "content": user_input}],
        "project_id": 1,
        "goal": user_input[:50],
        "is_retry": False
    }
    
    try:
        await asyncio.wait_for(run_agent_background(thread_id, inputs), timeout=300)
    except asyncio.TimeoutError:
        logger.error("⏱️ 超时")
    except Exception as e:
        logger.error(f"❌ 错误: {e}")
    
    logger.info("="*70)
    logger.info("追踪结束")
    logger.info("="*70)
    
    # Cleanup memory container
    global _memory_container
    if '_memory_container' in globals():
        try:
            await _memory_container.shutdown()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(test())
