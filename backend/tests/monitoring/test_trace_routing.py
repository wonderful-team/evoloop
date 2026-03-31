#!/usr/bin/env python3
"""
追踪 Worker -> Supervisor 的路由流程，诊断为什么反复迭代
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
logger = logging.getLogger("trace_routing")

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

env_path = '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

async def init():
    """快速初始化"""
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
    
    try:
        from app.core.memory import memory_manager
        await memory_manager.initialize()
    except:
        pass
    
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


async def trace_test():
    await init()
    
    from app.core.engine.background_agent import run_agent_background
    from app.core.monitoring.activity import activity_monitor
    from app.infrastructure.cache import cache
    
    thread_id = f"trace-{datetime.now().strftime('%H%M%S')}"
    user_input = "帮我写一个 Python 函数，计算斐波那契数列"
    
    logger.info("="*70)
    logger.info(f"🕵️ 路由追踪测试")
    logger.info(f"Thread: {thread_id}")
    logger.info(f"输入: {user_input}")
    logger.info("="*70)
    
    inputs = {
        "messages": [{"type": "human", "content": user_input}],
        "project_id": 1,
        "goal": user_input[:50],
        "is_retry": False
    }
    
    iteration = 0
    max_iterations = 15  # 最多追踪15次迭代
    
    async def monitor():
        nonlocal iteration
        prev_step_count = 0
        prev_node_names = []
        
        while iteration < max_iterations:
            await asyncio.sleep(3)
            
            activity = await activity_monitor.get_activity(thread_id)
            if not activity:
                continue
            
            steps = activity.get('steps', [])
            status = activity.get('status', 'unknown')
            
            if len(steps) > prev_step_count:
                # 有新步骤，分析变化
                new_steps = steps[prev_step_count:]
                for step in new_steps:
                    node_name = step.get('name', 'N/A')
                    node_status = step.get('status', '?')
                    logger.info(f"[Step {step.get('id')}] {node_name} ({node_status})")
                    
                    # 关键：检测 Supervisor->Worker 转换
                    if prev_node_names and 'Supervisor' in prev_node_names[-1] and 'Worker' in node_name:
                        iteration += 1
                        logger.warning(f"\n{'='*70}")
                        logger.warning(f"🔄 迭代 #{iteration}: Supervisor -> Worker")
                        logger.warning(f"{'='*70}")
                        
                        # 尝试读取 blackboard
                        try:
                            key = f"evoloop:activity:{thread_id}"
                            data = await cache.hgetall(key)
                            if data:
                                import json
                                steps_data = data.get('steps', '[]')
                                if isinstance(steps_data, str):
                                    steps_data = json.loads(steps_data)
                                logger.info(f"   当前步骤数: {len(steps_data)}")
                        except Exception as e:
                            logger.debug(f"   读取缓存失败: {e}")
                
                prev_step_count = len(steps)
                prev_node_names = [s.get('name', '') for s in steps]
                
                # 检测结束
                if status in ('done', 'completed', 'finished'):
                    logger.info(f"\n✅ Agent 完成! 状态: {status}")
                    return
    
    monitor_task = asyncio.create_task(monitor())
    
    try:
        await asyncio.wait_for(run_agent_background(thread_id, inputs), timeout=300)
    except asyncio.TimeoutError:
        logger.error("⏱️ 超时")
    except Exception as e:
        logger.error(f"❌ 错误: {e}")
    
    monitor_task.cancel()
    try:
        await monitor_task
    except:
        pass
    
    logger.info("\n" + "="*70)
    logger.info("📊 追踪结束")
    logger.info(f"总迭代次数: {iteration}")
    logger.info("="*70)


if __name__ == "__main__":
    asyncio.run(trace_test())
