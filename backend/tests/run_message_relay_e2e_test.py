#!/usr/bin/env python3
"""
消息中继端到端测试脚本（核心逻辑）

职责：
1. 登录获取 token
2. 通过真实 /api/v1/chat 发起多轮对话（thread_id 由后端首轮自动生成）
3. 轮询等待每轮 assistant 回复写入 SQLite
4. 触发增量同步到 Member Center
5. 验证 SQLite 与 MySQL 数据一致

由 tests/run_message_relay_e2e.sh 编排调用。
"""

import argparse
import asyncio
import logging
import os
import sqlite3
import subprocess
import sys
import time

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SQLITE_DB = os.path.expanduser("~/.evoloop/database/backend.db")
BACKEND_API_URL = "http://127.0.0.1:20160/api/v1"
TEST_PROJECT_ID = 99


# ==================== Auth ====================


async def _login() -> str:
    """Login via EvoCloud HTTP client (direct to MC)."""
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    evocloud_manager.initialize()

    client = evocloud_manager.api
    login_res = await client.login("preterchan", "hellomylife")
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    logger.info("[Auth] Login successful.")
    return token


# ==================== Chat ====================


async def _send_chat(
    client: httpx.AsyncClient,
    token: str,
    message: str,
    thread_id: str | None,
) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload: dict = {"message": message, "project_id": TEST_PROJECT_ID}
    # 真实 /chat 接口：第一轮不传 thread_id，由后端自动生成
    if thread_id is not None:
        payload["thread_id"] = thread_id

    resp = await client.post(
        f"{BACKEND_API_URL}/chat", json=payload, headers=headers, timeout=10
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Chat request failed: {resp.status_code} {resp.text}")
    return resp.json()


async def _poll_for_assistant_response(
    thread_id: str, turn: int, timeout: int = 180
) -> int:
    """轮询直到第 turn 轮出现 assistant 回复。返回当前总消息数。"""
    conn = sqlite3.connect(SQLITE_DB)
    try:
        for i in range(timeout):
            rows = conn.execute(
                "SELECT role, sequence_number, status FROM messages "
                "WHERE thread_id = ? ORDER BY sequence_number",
                (thread_id,),
            ).fetchall()
            # 后端 message role 为 'ai'，不是 'assistant'
            ai_count = sum(1 for r in rows if r[0] == "ai")
            if ai_count >= turn:
                logger.info(
                    f"[Poll] Turn {turn} ai replied after {i}s "
                    f"({len(rows)} messages total)"
                )
                return len(rows)
            time.sleep(1)
        raise TimeoutError(f"Turn {turn} ai did not reply within {timeout}s")
    finally:
        conn.close()


# ==================== Sync ====================


async def _trigger_sync():
    """触发增量同步。"""
    from app.core.evocloud import evocloud_manager
    from app.core.evocloud.bridge.conversation_sync import get_conversation_sync_manager

    await evocloud_manager.start()
    manager = get_conversation_sync_manager(
        evocloud_manager.api,
        evocloud_manager.link.device_key,
    )
    await manager.incremental_sync()
    logger.info("[Sync] Incremental sync triggered.")
    await asyncio.sleep(2)


# ==================== Verify ====================


def _verify_mysql(thread_id: str, sqlite_rows: list) -> bool:
    logger.info("[Verify] Checking MySQL data...")
    container_id = (
        subprocess.check_output(["docker", "ps", "--filter", "name=mysql", "-q"])
        .strip()
        .decode()
    )

    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container_id,
            "mysql",
            "-uroot",
            "-padmin888",
            "b2c_mall",
            "-e",
            f"SELECT id, role, content, hex(content) as hex_content, sequence_number "
            f"FROM evoloop_messages WHERE thread_id = '{thread_id}' ORDER BY sequence_number",
        ],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    lines = [
        line for line in output.split("\n") if line and not line.startswith("mysql:")
    ]
    if len(lines) < 2:
        logger.error("[Verify] No messages found in MySQL")
        return False

    header = lines[0].split("\t")
    mysql_rows = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) >= len(header):
            mysql_rows.append(dict(zip(header, parts, strict=True)))

    if len(sqlite_rows) != len(mysql_rows):
        logger.error(
            f"[Verify] Count mismatch: SQLite={len(sqlite_rows)}, MySQL={len(mysql_rows)}"
        )
        return False

    sqlite_conn = sqlite3.connect(SQLITE_DB)
    try:
        for sq_row, mq_row in zip(sqlite_rows, mysql_rows, strict=True):
            sq_id, sq_role, _, sq_seq, _ = sq_row
            sq_hex = sqlite_conn.execute(
                "SELECT hex(content) FROM messages WHERE id = ?", (sq_id,)
            ).fetchone()[0]
            mq_hex = mq_row.get("hex_content", "")
            mq_role = mq_row.get("role", "")
            mq_seq = mq_row.get("sequence_number", "")

            if sq_role != mq_role or str(sq_seq) != str(mq_seq) or sq_hex != mq_hex:
                logger.error(
                    f"[Verify] Mismatch at seq={sq_seq}: "
                    f"role SQLite={sq_role} MySQL={mq_role}, "
                    f"seq SQLite={sq_seq} MySQL={mq_seq}, "
                    f"hex SQLite={sq_hex} MySQL={mq_hex}"
                )
                return False
    finally:
        sqlite_conn.close()

    logger.info(
        f"[Verify] All {len(sqlite_rows)} messages match between SQLite and MySQL"
    )
    return True


# ==================== Main ====================


async def main():
    parser = argparse.ArgumentParser(description="Message Relay E2E Core Test")
    parser.add_argument(
        "--turns", type=int, default=2, help="Number of conversation turns"
    )
    parser.add_argument("--skip-service-check", action="store_true")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Message Relay E2E Core Test")
    logger.info(f"Turns: {args.turns}")
    logger.info("=" * 60)

    if not args.skip_service_check:
        import socket

        for port, name in [(9001, "Gateway"), (9002, "MC PHP"), (20160, "Backend API")]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    raise RuntimeError(f"{name} is not running on port {port}")

    token = await _login()

    thread_id = None
    async with httpx.AsyncClient() as client:
        for turn in range(1, args.turns + 1):
            if turn == args.turns:
                msg = f"这是第{turn}轮测试消息，请回复时包含一个 emoji 🙌 并简单问候。"
            else:
                msg = f"这是第{turn}轮测试消息，请简单回复。"
            logger.info(f"[Chat] Turn {turn}: {msg}")
            result = await _send_chat(client, token, msg, thread_id)
            if thread_id is None:
                thread_id = result.get("thread_id")
                logger.info(f"[Chat] Backend created thread_id: {thread_id}")
            logger.info(f"[Chat] Turn {turn} queued: {result}")

            await _poll_for_assistant_response(thread_id, turn, timeout=180)

    if not thread_id:
        raise RuntimeError("No thread_id created")

    # 读取最终 SQLite 消息
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_rows = sqlite_conn.execute(
        "SELECT id, role, content, sequence_number, sync_status "
        "FROM messages WHERE thread_id = ? ORDER BY sequence_number",
        (thread_id,),
    ).fetchall()
    sqlite_conn.close()
    logger.info(
        f"[Result] Thread {thread_id} has {len(sqlite_rows)} messages in SQLite"
    )

    await _trigger_sync()

    if not _verify_mysql(thread_id, sqlite_rows):
        raise RuntimeError("MySQL verification failed")

    logger.info("✅ MESSAGE RELAY E2E TEST PASSED")
    logger.info(f"Thread ID: {thread_id}")


if __name__ == "__main__":
    asyncio.run(main())
