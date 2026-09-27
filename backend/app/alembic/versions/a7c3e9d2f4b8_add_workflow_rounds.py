"""Workflow rounds: trigger moved onto task_workflows + per-round stage marking

轮次化周期工作流（触发/编排/执行三分离）：
- task_workflows 增加触发器三件套（trigger_spec/next_run_at/round_no）——
  周期语义从任务上移到编排层；
- project_tasks 增 workflow_round 一等列——每轮 spawn 的阶段任务标轮，
  供轮次查询/战报/（后续）画布折叠使用；不进 task_data（阶段八纪律）。

Revision ID: a7c3e9d2f4b8
Revises: d8e2f4b6a9c1
Create Date: 2026-09-25 10:40:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c3e9d2f4b8"
down_revision = "d8e2f4b6a9c1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_workflows",
        sa.Column("trigger_spec", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "task_workflows",
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_task_workflows_next_run_at"),
        "task_workflows",
        ["next_run_at"],
        unique=False,
    )
    op.add_column(
        "task_workflows",
        sa.Column("round_no", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_tasks",
        sa.Column("workflow_round", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("project_tasks", "workflow_round")
    op.drop_column("task_workflows", "round_no")
    op.drop_index(op.f("ix_task_workflows_next_run_at"), table_name="task_workflows")
    op.drop_column("task_workflows", "next_run_at")
    op.drop_column("task_workflows", "trigger_spec")
