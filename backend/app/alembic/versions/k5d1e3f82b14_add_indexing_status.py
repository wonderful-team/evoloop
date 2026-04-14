"""
Add indexing status columns

Revision ID: k5d1e3f82b14
Revises: j4c9d2e71a03
Create Date: 2026-03-03

This migration adds tracking for repository indexing state:
- indexing_status: pending, in_progress, completed, failed, not_needed
- last_indexed_at: When the repository was last successfully indexed
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k5d1e3f82b14"
down_revision: Union[str, None] = "j4c9d2e71a03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add indexing_status column
    op.add_column(
        "repositories",
        sa.Column("indexing_status", sa.String(50), nullable=True, default="pending")
    )

    # Add last_indexed_at column
    op.add_column(
        "repositories",
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Create index on indexing_status for efficient filtering
    op.create_index(
        "ix_repositories_indexing_status",
        "repositories",
        ["indexing_status"],
        unique=False
    )

    # Migrate existing data:
    # - Projects with sync_status in ("DETECTED", "IGNORED") -> not_needed
    # - Projects with sync_status in ("SYNCED", "PENDING_CREATION") and has files -> completed
    # - Projects with sync_status in ("SYNCED", "PENDING_CREATION") and no files -> pending
    op.execute("""
        UPDATE repositories
        SET indexing_status = CASE
            WHEN sync_status IN ('DETECTED', 'IGNORED') THEN 'not_needed'
            WHEN sync_status IN ('SYNCED', 'PENDING_CREATION') THEN 'pending'
            ELSE 'pending'
        END
        WHERE indexing_status IS NULL
    """)

    # Set default value for future inserts
    op.alter_column("repositories", "indexing_status", nullable=False, server_default="pending")


def downgrade() -> None:
    # Remove indexes
    op.drop_index("ix_repositories_indexing_status", table_name="repositories")

    # Remove columns
    op.drop_column("repositories", "last_indexed_at")
    op.drop_column("repositories", "indexing_status")
