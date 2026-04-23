"""add_maintenance_reports_table

Revision ID: 42f7ec7e40d5
Revises: b7408b54ac53
Create Date: 2026-04-23 21:45:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "42f7ec7e40d5"
down_revision = "b7408b54ac53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("report_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_reports_timestamp", "maintenance_reports", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_maintenance_reports_timestamp", table_name="maintenance_reports")
    op.drop_table("maintenance_reports")
