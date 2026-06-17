"""add_relative_path_to_repositories

Revision ID: f5c8a2d1e9b4
Revises: ebc64340ba7d
Create Date: 2026-06-17 17:30:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f5c8a2d1e9b4"
down_revision = "ebc64340ba7d"
branch_labels = None
depends_on = None


def upgrade():
    # Add relative_path column to repositories table
    op.add_column(
        "repositories",
        sa.Column("relative_path", sa.String(length=1024), nullable=True),
    )
    op.create_index(
        "ix_repositories_relative_path",
        "repositories",
        ["relative_path"],
        unique=False,
    )

    # Backfill relative_path from local_path where possible
    op.execute("""
        UPDATE repositories
        SET relative_path = local_path
        WHERE relative_path IS NULL AND local_path IS NOT NULL
    """)


def downgrade():
    op.drop_index("ix_repositories_relative_path", table_name="repositories")
    op.drop_column("repositories", "relative_path")
