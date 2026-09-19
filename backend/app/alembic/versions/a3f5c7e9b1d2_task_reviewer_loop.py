"""task reviewer loop: task_no, origin_thread_id, review_count

Revision ID: a3f5c7e9b1d2
Revises: f0a1b2c3d4e5
Create Date: 2026-09-19
"""

import sqlalchemy as sa
from alembic import op

revision = "a3f5c7e9b1d2"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_tasks", sa.Column("task_no", sa.Integer(), nullable=True)
    )
    op.create_index("ix_project_tasks_task_no", "project_tasks", ["task_no"])
    op.add_column(
        "project_tasks",
        sa.Column("origin_thread_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "project_tasks",
        sa.Column(
            "review_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("project_tasks", "review_count")
    op.drop_column("project_tasks", "origin_thread_id")
    op.drop_index("ix_project_tasks_task_no", table_name="project_tasks")
    op.drop_column("project_tasks", "task_no")
