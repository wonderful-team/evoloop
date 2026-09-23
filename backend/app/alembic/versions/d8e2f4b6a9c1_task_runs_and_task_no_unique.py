"""task_runs + project_task_no unique

Revision ID: d8e2f4b6a9c1
Revises: c4f7a1b9e2d3
Create Date: 2026-09-23

1) task_runs：任务与运行分离（过程记录层，attempt 历史/每轮 token/失败
   原因）。2) (project_id, task_no) 唯一索引：max+1 并发竞态从"静默重复
   编号"收敛为 IntegrityError → 服务端捕获重试。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d8e2f4b6a9c1"
down_revision = "c4f7a1b9e2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("tokens", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_runs_task_id", "task_runs", ["task_id"])
    op.create_index("ix_task_runs_thread_id", "task_runs", ["thread_id"])
    op.create_index("ix_task_runs_status", "task_runs", ["status"])

    # (project_id, task_no) 唯一：SQLite 不支持带 WHERE 的部分唯一索引跨方言
    # 简化；task_no 可空（历史行）——NULL 在唯一索引中互不冲突，安全。
    op.create_index(
        "uq_project_tasks_project_task_no",
        "project_tasks",
        ["project_id", "task_no"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_project_tasks_project_task_no", table_name="project_tasks"
    )
    op.drop_index("ix_task_runs_status", table_name="task_runs")
    op.drop_index("ix_task_runs_thread_id", table_name="task_runs")
    op.drop_index("ix_task_runs_task_id", table_name="task_runs")
    op.drop_table("task_runs")
