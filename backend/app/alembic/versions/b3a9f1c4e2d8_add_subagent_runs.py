"""add subagent_runs table for parallel subagent lifecycle persistence

Revision ID: b3a9f1c4e2d8
Revises: a7c3e8f2b1d9
Create Date: 2026-08-27

Phase A (docs/subagent-design.md §3.1): SubagentRun 持久化子 agent 生命周期，
支持并行 subagent 的查询/取消/崩溃恢复与聚合。
"""

import sqlalchemy as sa
from alembic import op

revision = "b3a9f1c4e2d8"
down_revision = "a7c3e8f2b1d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subagent_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("parent_thread_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("instruction", sa.String(), nullable=False),
        sa.Column("role_name", sa.String(), nullable=False),
        sa.Column("focus_paths", sa.String(), nullable=True),
        sa.Column("acceptance_criteria", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("tools_used", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_subagent_runs_parent_thread_id", "subagent_runs", ["parent_thread_id"])
    op.create_index("ix_subagent_runs_thread_id", "subagent_runs", ["thread_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_subagent_runs_thread_id", table_name="subagent_runs")
    op.drop_index("ix_subagent_runs_parent_thread_id", table_name="subagent_runs")
    op.drop_table("subagent_runs")