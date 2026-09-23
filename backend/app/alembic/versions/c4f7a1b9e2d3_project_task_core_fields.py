"""promote project task queue fields out of task_data

Revision ID: c4f7a1b9e2d3
Revises: b3e6f8a2c4d0
Create Date: 2026-09-23

The backfill deliberately reads JSON in Python instead of using database JSON
operators.  This keeps the migration usable on both SQLite and PostgreSQL.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "c4f7a1b9e2d3"
down_revision = "b3e6f8a2c4d0"
branch_labels = None
depends_on = None


def _as_task_data(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def upgrade() -> None:
    op.add_column("project_tasks", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column("project_tasks", sa.Column("priority", sa.String(length=20), nullable=True))
    op.add_column("project_tasks", sa.Column("category", sa.String(length=100), nullable=True))
    op.add_column("project_tasks", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("project_tasks", sa.Column("dependencies", sa.JSON(), nullable=True))
    op.add_column(
        "project_tasks",
        sa.Column("acceptance_criteria", sa.JSON(), nullable=True),
    )
    op.add_column(
        "project_tasks",
        sa.Column("workflow_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "project_tasks",
        sa.Column("dispatch_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("project_tasks", sa.Column("last_result", sa.Text(), nullable=True))
    op.add_column("project_tasks", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column(
        "project_tasks",
        sa.Column("review_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "project_tasks",
        sa.Column("workflow_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_tasks",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_index("ix_project_tasks_category", "project_tasks", ["category"])
    op.create_index("ix_project_tasks_workflow_id", "project_tasks", ["workflow_id"])

    tasks = sa.table(
        "project_tasks",
        sa.column("id", sa.String(length=36)),
        sa.column("task_data", sa.JSON()),
        sa.column("title", sa.String(length=255)),
        sa.column("priority", sa.String(length=20)),
        sa.column("category", sa.String(length=100)),
        sa.column("tags", sa.JSON()),
        sa.column("dependencies", sa.JSON()),
        sa.column("acceptance_criteria", sa.JSON()),
        sa.column("workflow_id", sa.String(length=36)),
        sa.column("dispatch_count", sa.Integer()),
        sa.column("last_result", sa.Text()),
        sa.column("last_error", sa.Text()),
        sa.column("review_pending", sa.Boolean()),
        sa.column("workflow_retry_count", sa.Integer()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(tasks.c.id, tasks.c.task_data)).mappings()
    for row in rows:
        data = _as_task_data(row["task_data"])
        values: dict[str, object] = {}
        for field in (
            "title",
            "priority",
            "category",
            "tags",
            "dependencies",
            "acceptance_criteria",
            "workflow_id",
            "last_result",
            "last_error",
        ):
            if field in data and data[field] is not None:
                values[field] = data[field]

        if "dispatch_count" in data and data["dispatch_count"] is not None:
            values["dispatch_count"] = int(data["dispatch_count"] or 0)
        if "review_pending" in data and data["review_pending"] is not None:
            values["review_pending"] = _as_bool(data["review_pending"])
        if "workflow_retry_count" in data and data["workflow_retry_count"] is not None:
            values["workflow_retry_count"] = int(data["workflow_retry_count"] or 0)

        if values:
            connection.execute(
                tasks.update().where(tasks.c.id == row["id"]).values(**values)
            )


def downgrade() -> None:
    op.drop_index("ix_project_tasks_workflow_id", table_name="project_tasks")
    op.drop_index("ix_project_tasks_category", table_name="project_tasks")
    for column in (
        "version",
        "workflow_retry_count",
        "review_pending",
        "last_error",
        "last_result",
        "dispatch_count",
        "workflow_id",
        "acceptance_criteria",
        "dependencies",
        "tags",
        "category",
        "priority",
        "title",
    ):
        op.drop_column("project_tasks", column)
