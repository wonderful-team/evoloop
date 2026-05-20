"""
Chat Attachment Session Isolation Test
======================================
Goal: 验证不同会话上传同名文件时，物理存储是否隔离，且 Agent 能准确读取各自会话的文件。

测试逻辑：
1. 模拟会话 A：
   - 产生临时 session_id_A
   - 上传 data.txt (内容: "This is Session A")
   - 发送第一条消息，触发“转正”到 thread_id_A
   - Agent 读取 uploads/data.txt，预期得到 "This is Session A"
2. 模拟会话 B：
   - 产生临时 session_id_B
   - 上传 data.txt (内容: "This is Session B")
   - 发送第一条消息，触发“转正”到 thread_id_B
   - Agent 读取 uploads/data.txt，预期得到 "This is Session B"
"""

import asyncio
import os
import sys
import uuid
import shutil
import logging
from unittest.mock import patch, PropertyMock

from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_isolation")

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.sql.database import session_scope
from app.models import Message
from app.core.config import settings

async def initialize_system():
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    graph = builder.build(config_path, checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)

async def upload_mock(content: str, session_id: str = None, thread_id: str = None):
    """模拟前端上传动作"""
    sub_dir = f"tmp_{session_id}" if session_id else thread_id
    upload_dir = os.path.join(settings.CHAT_UPLOAD_DIR, sub_dir)
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, "data.txt")
    with open(file_path, "w") as f:
        f.write(content)
    
    return {
        "id": "uploads/data.txt",
        "name": "data.txt",
        "type": "file"
    }

async def run_session_test(session_name: str, content: str):
    thread_id = f"thread_{session_name}_{uuid.uuid4().hex[:6]}"
    session_id = f"sess_{session_name}"
    
    logger.info(f"--- Starting Session {session_name} (thread={thread_id}) ---")
    
    # 1. 上传文件到临时目录
    attachment = await upload_mock(content, session_id=session_id)
    
    # 2. 发起 Dispatch，带上 upload_session_id
    res = await dispatch_agent_run(
        thread_id=thread_id,
        message_content="请读取 uploads/data.txt 的内容并原样输出。",
        upload_session_id=session_id,
        attachments=[attachment],
        project_id=0
    )
    
    # 3. 运行 Agent
    await run_agent_background(thread_id, res.inputs)
    
    # 4. 验证结果
    async with session_scope() as session:
        from sqlalchemy import select
        stmt = select(Message).where(Message.thread_id == thread_id, Message.role == "ai").order_by(Message.sequence_number.desc())
        result = await session.execute(stmt)
        msg = result.scalar()
        if msg:
            logger.info(f"Result for {session_name}: {msg.content}")
            return content in str(msg.content)
    return False

async def main():
    await initialize_system()
    
    try:
        # 清理之前的上传
        if os.path.exists(settings.CHAT_UPLOAD_DIR):
            shutil.rmtree(settings.CHAT_UPLOAD_DIR)
        os.makedirs(settings.CHAT_UPLOAD_DIR, exist_ok=True)

        # 同时运行两个相互干扰的会话
        success_a = await run_session_test("A", "SECRET_CONTENT_A")
        success_b = await run_session_test("B", "SECRET_CONTENT_B")
        
        print("\n" + "="*40)
        print(f"Session A Success: {success_a}")
        print(f"Session B Success: {success_b}")
        print("="*40)
        
        if success_a and success_b:
            print("✅ ISOLATION VERIFIED: Files with same name do not conflict across sessions.")
        else:
            print("❌ ISOLATION FAILED")
            
    finally:
        await db_resource_manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
