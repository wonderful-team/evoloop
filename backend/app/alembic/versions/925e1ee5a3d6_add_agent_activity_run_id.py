"""add agent_activities.run_id column for run isolation

Revision ID: 925e1ee5a3d6
Revises: 0984dfc539df
Create Date: 2026-08-06

run_id 隔离：旧 run 的取消/结束不得覆盖新 run 的活动状态（NEW_COMMAND 竞态）。
"""

import sqlalchemy as sa
from alembic import op

revision = "925e1ee5a3d6"
down_revision = "0984dfc539df"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_activities",
        sa.Column("run_id", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_activities", "run_id")
