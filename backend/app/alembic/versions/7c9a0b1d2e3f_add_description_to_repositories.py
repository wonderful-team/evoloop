"""add description column to repositories

Revision ID: 7c9a0b1d2e3f
Revises: 6a314534fcc4
Create Date: 2026-07-10 12:10:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7c9a0b1d2e3f"
down_revision = "6a314534fcc4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "repositories",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("repositories", "description")
