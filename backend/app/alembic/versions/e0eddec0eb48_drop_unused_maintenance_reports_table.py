"""drop unused maintenance_reports table

Revision ID: e0eddec0eb48
Revises: a7c3e9d2f4b8
Create Date: 2026-09-27 09:24:22.529733

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e0eddec0eb48'
down_revision = 'a7c3e9d2f4b8'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_maintenance_reports_timestamp", table_name="maintenance_reports", if_exists=True)
    op.drop_table("maintenance_reports", if_exists=True)


def downgrade():
    op.create_table(
        "maintenance_reports",
        sa.Column("id", sa.INTEGER(), nullable=False),
        sa.Column("timestamp", sa.DATETIME(), nullable=False),
        sa.Column("level", sa.VARCHAR(length=50), nullable=True),
        sa.Column("dry_run", sa.BOOLEAN(), nullable=True),
        sa.Column("duration_seconds", sa.FLOAT(), nullable=True),
        sa.Column("summary_json", sa.TEXT(), nullable=True),
        sa.Column("report_json", sa.TEXT(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_reports_timestamp", "maintenance_reports", ["timestamp"], unique=False)
