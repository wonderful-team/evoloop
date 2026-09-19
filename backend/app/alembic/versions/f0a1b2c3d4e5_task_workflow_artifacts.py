"""task workflow and artifact tables for staged agent workflows

Revision ID: f0a1b2c3d4e5
Revises: 8c1d5f7a9e3b
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "8c1d5f7a9e3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_workflows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column(
            "workflow_type", sa.String(length=64), nullable=False,
            server_default="commerce_growth_text",
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_workflows_project_id", "task_workflows", ["project_id"])
    op.create_index("ix_task_workflows_member_id", "task_workflows", ["member_id"])
    op.create_index("ix_task_workflows_status", "task_workflows", ["status"])

    op.create_table(
        "task_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="generated"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_artifacts_project_id", "task_artifacts", ["project_id"])
    op.create_index("ix_task_artifacts_workflow_id", "task_artifacts", ["workflow_id"])
    op.create_index("ix_task_artifacts_task_id", "task_artifacts", ["task_id"])
    op.create_index("ix_task_artifacts_stage", "task_artifacts", ["stage"])
    op.create_index("ix_task_artifacts_status", "task_artifacts", ["status"])


def downgrade() -> None:
    op.drop_table("task_artifacts")
    op.drop_table("task_workflows")
