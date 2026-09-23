"""Alembic 迁移回放冒烟测试：空库 → upgrade head → 终态 schema 断言。

验证真实迁移链（base → head）在干净 SQLite 上可完整回放（CI/新部署路径），
并锁定 HITL 终态迁移（b3e6f8a2c4d0）落库结果：
  - human_requests 带 resource_path / resource_action / expires_at 三列；
  - ix_human_requests_thread_resource 索引存在；
  - alembic_version 指向当前 head。

隔离方式：子进程 + EVOLOOP_APP_DATA_DIR 指向临时目录（不触碰开发库）。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[3]
HEAD_REVISION = "d8e2f4b6a9c1"


@pytest.mark.timeout(300)
def test_alembic_upgrade_head_on_empty_sqlite(tmp_path: Path) -> None:
    app_data = tmp_path / "appdata"
    (app_data / "database").mkdir(parents=True)

    env = {**os.environ, "EVOLOOP_APP_DATA_DIR": str(app_data)}
    alembic_bin = Path(sys.executable).parent / "alembic"
    result = subprocess.run(
        [str(alembic_bin), "-c", "alembic.ini", "upgrade", "head"],
        cwd=str(BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=280,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head 失败:\nstdout={result.stdout[-2000:]}\nstderr={result.stderr[-3000:]}"
    )

    db_path = app_data / "database" / "backend.db"
    assert db_path.exists(), f"迁移未产生数据库: {sorted(p.name for p in (app_data / 'database').iterdir())}"

    conn = sqlite3.connect(str(db_path))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(human_requests)")}
        assert {
            "resource_path",
            "resource_action",
            "expires_at",
        } <= cols, f"终态列缺失: {sorted(cols)}"

        indexes = {r[1] for r in conn.execute("PRAGMA index_list(human_requests)")}
        assert "ix_human_requests_thread_resource" in indexes, indexes

        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert version is not None and version[0] == HEAD_REVISION, version

        # 双轨另一侧：messages 表可写且含终态判死链路依赖的列
        msg_cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        assert {"tool_call_id", "meta_data", "status"} <= msg_cols
    finally:
        conn.close()
