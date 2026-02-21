"""Add skill lifecycle enhancement fields

Revision ID: i3b8c42e56f2
Revises: h2a7b8c31d95
Create Date: 2026-02-08

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "i3b8c42e56f2"
down_revision = "h2a7b8c31d95"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add skill lifecycle enhancement fields
    op.add_column(
        "learned_skills",
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "learned_skills",
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "learned_skills",
        sa.Column("promotion_history", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learned_skills", "promotion_history")
    op.drop_column("learned_skills", "last_failure_at")
    op.drop_column("learned_skills", "last_success_at")
