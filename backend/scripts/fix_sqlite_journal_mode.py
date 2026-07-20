#!/usr/bin/env python3
"""
安全的 SQLite journal_mode 切换脚本。

使用方式（必须停止所有持有数据库的进程后执行）：
    python scripts/fix_sqlite_journal_mode.py

功能：
1. 将 WAL 文件中的数据 checkpoint 到主数据库
2. 切换 journal_mode 为 DELETE
3. 删除 WAL 和 SHM 文件
4. 验证切换结果
"""

import os
import sqlite3
import sys

DB_PATH = os.path.expanduser("~/.evoloop/backend.db")


def main():
    if not os.path.exists(DB_PATH):
        print(f"数据库不存在: {DB_PATH}")
        sys.exit(1)

    # Check current journal mode
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    current_mode = cursor.fetchone()[0]
    print(f"当前 journal_mode: {current_mode}")

    if current_mode == "delete":
        print("已经是 DELETE 模式，无需切换")
        conn.close()
        return

    # Check WAL file size
    wal_path = DB_PATH + "-wal"
    shm_path = DB_PATH + "-shm"
    if os.path.exists(wal_path):
        wal_size = os.path.getsize(wal_path)
        print(f"WAL 文件大小: {wal_size / 1024 / 1024:.1f} MB")

    print("\n开始切换...")

    # Step 1: Checkpoint WAL to main database
    print("1. Checkpoint WAL 数据到主数据库...")
    cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    result = cursor.fetchone()
    print(f"   Checkpoint 结果: busy={result[0]}, log={result[1]}, checkpointed={result[2]}")

    # Step 2: Switch to DELETE mode
    print("2. 切换 journal_mode 为 DELETE...")
    cursor.execute("PRAGMA journal_mode=DELETE")
    new_mode = cursor.fetchone()[0]
    print(f"   新模式: {new_mode}")

    conn.commit()
    conn.close()

    # Step 3: Verify WAL/SHM files are removed
    if os.path.exists(wal_path):
        print(f"3. WAL 文件仍存在，手动删除...")
        os.remove(wal_path)
    if os.path.exists(shm_path):
        print(f"   SHM 文件仍存在，手动删除...")
        os.remove(shm_path)

    # Verify
    conn2 = sqlite3.connect(DB_PATH)
    cursor2 = conn2.cursor()
    cursor2.execute("PRAGMA journal_mode")
    verify_mode = cursor2.fetchone()[0]
    conn2.close()

    print(f"\n✅ 切换完成！当前 journal_mode: {verify_mode}")
    print(f"数据库路径: {DB_PATH}")


if __name__ == "__main__":
    main()
