#!/usr/bin/env python3
"""
Multi-Turn Conversation Sync E2E Test

参考 tests/run_multi_turn_e2e_test.py 改造：
- 不跑 LLM Agent（省时间/费用）
- 在 SQLite 中构造一个多轮对话（3 轮 human + assistant）
- 触发 ConversationSyncManager 增量同步到 MC
- 验证 MySQL 中消息数量、顺序、内容字节级一致
"""

import argparse
import asyncio
import logging
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

TEST_PROJECT_ID = 99
TEST_LOG_FILE = os.path.join(os.path.dirname(__file__), "multi_turn_sync_e2e_test.log")

logger = logging.getLogger(__name__)


async def _init_backend():
    from app.infrastructure.database.resource_manager import db_resource_manager
    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    logger.info("[Test] Initializing EvoCloud Manager...")
    evocloud_manager.initialize()

    client = evocloud_manager.api
    login_res = await client.login("preterchan", "hellomylife")
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    logger.info("[Test] Login successful.")

    # 启动 conversation sync manager（会重新注册/获取 device_key）
    await evocloud_manager.start()
    logger.info(f"[Test] EvoCloud started. Device key: {evocloud_manager.link.device_key}")


async def _seed_multi_turn_conversation(thread_id: str):
    """在 SQLite 中插入 3 轮对话，每轮 human + assistant。"""
    from datetime import datetime, timezone
    from sqlalchemy import insert
    from app.infrastructure.database.sql.database import get_db_session
    from app.models import Conversation as ConversationModel
    from app.models import Message as MessageModel

    now = datetime.now(timezone.utc)
    base_ts = int(now.timestamp())

    async with get_db_session() as db:
        # 会话
        await db.execute(
            insert(ConversationModel).values(
                id=thread_id,
                project_id=TEST_PROJECT_ID,
                member_id=1,
                title="多轮对话同步测试",
                created_at=now,
                updated_at=now,
                sync_status="pending",
            )
        )

        turns = [
            ("human", "你好，请帮我写一个 Python 函数，计算两个数的和。✅"),
            ("assistant", "好的，这是一个简单的 Python 函数：\n\ndef add(a, b):\n    return a + b\n\n你可以直接调用 `add(1, 2)`。"),
            ("human", "能不能再加一个异常处理，防止传入非数字？"),
            ("assistant", "当然可以，改进后的版本如下：\n\ndef add(a, b):\n    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):\n        raise TypeError('参数必须是数字')\n    return a + b"),
            ("human", "最后帮我写个单元测试。"),
            ("assistant", "使用 unittest 的示例：\n\nimport unittest\n\nclass TestAdd(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n\nif __name__ == '__main__':\n    unittest.main()"),
        ]

        msg_values = []
        for seq, (role, content) in enumerate(turns, start=1):
            msg_values.append({
                "id": str(uuid.uuid4()),
                "thread_id": thread_id,
                "member_id": 1,
                "project_id": TEST_PROJECT_ID,
                "role": role,
                "content": content,
                "created_at": datetime.fromtimestamp(base_ts + seq, tz=timezone.utc),
                "updated_at": datetime.fromtimestamp(base_ts + seq, tz=timezone.utc),
                "sequence_number": seq,
                "action_type": "text",
                "content_type": "text",
                "is_visible": True,
                "status": "completed",
                "sync_status": "pending",
                "meta_data": {},
            })

        await db.execute(insert(MessageModel).values(msg_values))
        await db.commit()

        logger.info(f"[Test] Seeded {len(turns)} messages in thread {thread_id}")
        return [m["id"] for m in msg_values]


async def _trigger_sync(thread_id: str):
    """触发增量同步。"""
    from app.core.evocloud.bridge.conversation_sync import get_conversation_sync_manager
    from app.core.evocloud import evocloud_manager

    manager = get_conversation_sync_manager(
        evocloud_manager.api,
        evocloud_manager.link.device_key,
    )
    await manager.incremental_sync()
    logger.info(f"[Test] Incremental sync triggered for thread {thread_id}")

    # 等待任务执行（embedded 模式下 .delay 同步执行，但仍给一点缓冲）
    await asyncio.sleep(2)


async def _verify_mysql(thread_id: str, expected_msg_ids: list):
    """验证 MySQL 数据。"""
    import subprocess
    import sqlite3

    db_path = os.path.expanduser("~/.evoloop/database/backend.db")

    # SQLite 原文
    sqlite_conn = sqlite3.connect(db_path)
    sqlite_rows = sqlite_conn.execute(
        "SELECT id, role, content, hex(content) as hex_content, sequence_number FROM messages WHERE thread_id = ? ORDER BY sequence_number",
        (thread_id,),
    ).fetchall()
    sqlite_conn.close()

    logger.info(f"[Test] SQLite has {len(sqlite_rows)} messages")

    # MySQL 数据
    container_id = subprocess.check_output(
        ["docker", "ps", "--filter", "name=mysql", "-q"]
    ).strip().decode()

    cmd = [
        "docker", "exec", "-i", container_id,
        "mysql", "-uroot", "-padmin888", "b2c_mall",
        "-e",
        f"SELECT id, role, content, hex(content) as hex_content, sequence_number FROM evoloop_messages WHERE thread_id = '{thread_id}' ORDER BY sequence_number"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    mysql_output = result.stdout.strip()

    logger.info(f"[Test] MySQL raw output:\n{mysql_output}")

    # 解析 MySQL 输出（简单按行解析）
    lines = [line for line in mysql_output.split("\n") if line and not line.startswith("mysql:")]
    if len(lines) < 2:
        raise AssertionError("MySQL 中没有查询到消息")

    header = lines[0].split("\t")
    mysql_rows = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) >= len(header):
            row = dict(zip(header, parts))
            mysql_rows.append(row)

    logger.info(f"[Test] MySQL has {len(mysql_rows)} messages")

    # 验证数量
    if len(sqlite_rows) != len(mysql_rows):
        raise AssertionError(f"消息数量不一致: SQLite={len(sqlite_rows)}, MySQL={len(mysql_rows)}")

    # 验证每条消息
    for sq_row, mq_row in zip(sqlite_rows, mysql_rows):
        sq_id, sq_role, sq_content, sq_hex, sq_seq = sq_row
        mq_id = mq_row.get("id", "")
        mq_role = mq_row.get("role", "")
        mq_content = mq_row.get("content", "")
        mq_hex = mq_row.get("hex_content", "")
        mq_seq = mq_row.get("sequence_number", "")

        if sq_id != mq_id:
            raise AssertionError(f"ID 不一致: SQLite={sq_id}, MySQL={mq_id}")
        if sq_role != mq_role:
            raise AssertionError(f"Role 不一致: SQLite={sq_role}, MySQL={mq_role}")
        if str(sq_seq) != str(mq_seq):
            raise AssertionError(f"Sequence 不一致: SQLite={sq_seq}, MySQL={mq_seq}")
        if sq_hex != mq_hex:
            raise AssertionError(f"Content bytes 不一致 (seq={sq_seq}):\nSQLite={sq_hex}\nMySQL={mq_hex}")

    logger.info("✓ 所有消息内容和元数据一致")


async def main():
    parser = argparse.ArgumentParser(description="Multi-Turn Conversation Sync E2E Test")
    parser.add_argument("--timeout", type=int, default=120, help="Test timeout in seconds")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("=" * 60)
    logger.info("Multi-Turn Conversation Sync E2E Test")
    logger.info("=" * 60)

    thread_id = f"multi-turn-sync-{uuid.uuid4().hex[:8]}"

    try:
        await asyncio.wait_for(_init_backend(), timeout=args.timeout)
        msg_ids = await _seed_multi_turn_conversation(thread_id)
        await _trigger_sync(thread_id)
        await _verify_mysql(thread_id, msg_ids)

        logger.info("✅ MULTI-TURN SYNC TEST PASSED")
        logger.info(f"Thread ID: {thread_id}")

    except Exception as e:
        logger.exception(f"❌ TEST FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
