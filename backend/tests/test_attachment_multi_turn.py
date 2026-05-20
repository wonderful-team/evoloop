"""
Multi-Turn File Attachment Context Test
=========================================
Goal: 验证 Agent 在多轮对话中是否能持续感知第一轮上传的文件。

测试场景：
1. 上传文件（抖音本地样本数据.xlsx）
2. Turn 1：请统计一下文件中2026年总消费人数、消费金额、会员客单价、平均购买频次分别是多少？
3. Turn 2：我只要2026年的，你确定你统计的是2026年的吗？
4. Turn 3：换个问题，2026年直营的总消费人数是多少？

分析目标：
- 日志打印 HumanMessage 完整 content（包含 content_blocks 结构）
- 追踪每轮 Supervisor 接收到的消息历史
- 明确 attachment 在第 2 轮是否仍然在消息历史中
"""

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

# ---- 关键：在普通 INFO 之上，打印 CONTEXT_TRACE 级别日志 ----
CONTEXT_TRACE = 15
logging.addLevelName(CONTEXT_TRACE, "CTX")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/multi_turn_file_test.log", mode="w", encoding="utf-8"),
    ]
)
# 抑制无关噪音
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("alembic").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger = logging.getLogger("test_attachment_context")

from app.core.evocloud import evocloud_manager
from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.sql.database import session_scope
from app.models import Message
from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
from app.core.config import settings


# =========================================================================
# 关键 Monkey Patch：拦截 Supervisor 接收到的消息历史，打印完整上下文
# =========================================================================
ORIGINAL_FILTER = None

def _patched_filter_messages(messages):
    """拦截 Supervisor 消息过滤，记录过滤前后的完整内容"""
    logger.log(CONTEXT_TRACE, "\n" + "="*80)
    logger.log(CONTEXT_TRACE, f"[CTX-TRACE] Supervisor 接收消息历史 (共 {len(messages)} 条):")
    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        name = getattr(msg, "name", None)
        content = msg.content
        if isinstance(content, list):
            # content_blocks 格式：检查是否有文件引用
            has_file_ref = any(
                isinstance(b, dict) and "uploads/" in str(b.get("text", ""))
                for b in content
            )
            content_preview = f"[content_blocks × {len(content)}]{' ⚠️ 含文件引用' if has_file_ref else ' (无文件引用)'}"
            # 详细打印第一条（通常是用户消息）
            if i < 3:
                for j, block in enumerate(content):
                    if isinstance(block, dict):
                        text = block.get("text", "")[:300]
                        logger.log(CONTEXT_TRACE, f"  Block[{j}]: {text}")
        else:
            content_preview = str(content)[:200]
        label = f"[{name}]" if name else ""
        logger.log(CONTEXT_TRACE, f"  [{i}] {msg_type}{label}: {content_preview}")
    logger.log(CONTEXT_TRACE, "="*80 + "\n")
    
    if ORIGINAL_FILTER:
        result = ORIGINAL_FILTER(messages)
        logger.log(CONTEXT_TRACE, f"[CTX-TRACE] 过滤后剩余 {len(result)} 条消息")
        return result
    return messages


async def upload_file_to_global(file_path: str) -> dict:
    """直接调用后端存储逻辑上传文件，返回 attachment dict"""
    from app.core.config import settings
    
    upload_dir = settings.CHAT_UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    
    filename = os.path.basename(file_path)
    target = os.path.join(upload_dir, filename)
    if os.path.exists(target):
        os.remove(target)
    shutil.copy2(file_path, target)
    
    logger.info(f"[Upload] 文件已复制至: {target}")
    
    return {
        "id": f"uploads/{filename}",  # 这是 attachment.id，即文件的逻辑路径
        "url": f"uploads/{filename}",
        "name": filename,
        "type": "file",
    }


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


async def run_test():
    global ORIGINAL_FILTER
    
    # 安装消息历史拦截器
    from app.core.engine.nodes.supervisor import SupervisorNode
    ORIGINAL_FILTER = SupervisorNode._filter_messages_for_supervisor
    SupervisorNode._filter_messages_for_supervisor = staticmethod(_patched_filter_messages)
    logger.info("[Patch] SupervisorNode._filter_messages_for_supervisor 已拦截")
    
    try:
        await initialize_system()
        
        # 上传测试文件
        xlsx_path = os.path.expanduser("~/Downloads/抖音本地样本数据.xlsx")
        if not os.path.exists(xlsx_path):
            logger.error(f"测试文件不存在: {xlsx_path}")
            return
        attachment = await upload_file_to_global(xlsx_path)
        logger.info(f"[Upload] attachment = {json.dumps(attachment, ensure_ascii=False)}")
        
        project_id = 0  # 全局模式
        thread_id = f"file-ctx-test-{uuid.uuid4().hex[:6]}"
        
        conversation = [
            # Turn 1：带文件附件
            {
                "content": "请统计一下文件中2026年总消费人数、消费金额、会员客单价、平均购买频次分别是多少？",
                "attachments": [attachment],
            },
            # Turn 2：不带附件，考验 Agent 是否记得文件
            {
                "content": "我只要2026年的，你确定你统计的是2026年的吗？",
                "attachments": [],
            },
            # Turn 3：再次考验
            {
                "content": "换个问题，2026年直营的总消费人数是多少？",
                "attachments": [],
            },
        ]
        
        client = evocloud_manager.api
        login_res = await client.login("preterchan", "hellomylife")
        if not login_res.get("success"):
            logger.error(f"Login failed: {login_res}")
            return
        TOKEN = login_res["token"]
        
        with patch("app.core.evocloud.evocloud_manager.get_token", return_value=TOKEN), \
             patch.object(EvoCloudHTTPClient, "root_url", new_callable=PropertyMock, return_value="https://evoloop.develop-assistant.cn"):
            
            for turn_no, turn in enumerate(conversation, 1):
                print(f"\n{'!'*60}")
                print(f"!!! TURN {turn_no}: {turn['content']}")
                if turn['attachments']:
                    print(f"!!! Attachments: {[a['name'] for a in turn['attachments']]}")
                print(f"{'!'*60}\n")
                
                dispatch_res = await dispatch_agent_run(
                    thread_id=thread_id,
                    message_content=turn["content"],
                    project_id=project_id,
                    attachments=turn.get("attachments"),
                )
                
                if dispatch_res.status != "queued":
                    print(f"❌ Dispatch failed at turn {turn_no}: {dispatch_res.error}")
                    break
                
                # ---- 打印当轮 inputs 中的 content_blocks ----
                messages_in = dispatch_res.inputs.get("messages", [])
                print(f"\n[DEBUG] Turn {turn_no} - dispatch inputs.messages:")
                for m in messages_in:
                    content = m.get("content", "")
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                print(f"  TEXT BLOCK (first 500 chars):\n{block['text'][:500]}")
                    else:
                        print(f"  CONTENT: {str(content)[:300]}")
                
                await run_agent_background(thread_id, dispatch_res.inputs)
                
                # 打印 AI 回复
                async with session_scope() as session:
                    from sqlalchemy import select
                    stmt = select(Message).where(
                        Message.thread_id == thread_id,
                        Message.role == "ai"
                    ).order_by(Message.sequence_number.desc()).limit(1)
                    res = await session.execute(stmt)
                    last_ai = res.scalar()
                    if last_ai:
                        print(f"\n✅ Turn {turn_no} AI Response:\n{str(last_ai.content)[:600]}\n")
                    else:
                        print(f"⚠️ Turn {turn_no}: No AI response found")
        
        # 最终分析
        print(f"\n{'='*60}")
        print(f"CHECKPOINT LOG: /tmp/multi_turn_file_test.log")
        print(f"Thread ID: {thread_id}")
        print(f"{'='*60}")
        
        async with session_scope() as session:
            from sqlalchemy import select
            stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
            res = await session.execute(stmt)
            all_msgs = res.scalars().all()
            print(f"\nTotal messages: {len(all_msgs)}")
            for m in all_msgs:
                icon = "👤" if m.role == "human" else "🤖" if m.role == "ai" else "🛠️"
                print(f"{icon} [{m.sequence_number}] {m.role.upper()}: {str(m.content)[:80]}...")
    
    finally:
        await db_resource_manager.shutdown()
        logger.info("--- Cleanup Complete ---")


if __name__ == "__main__":
    asyncio.run(run_test())
