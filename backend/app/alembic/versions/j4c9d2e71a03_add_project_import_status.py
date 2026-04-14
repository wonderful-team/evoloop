"""
Add project import status columns

Revision ID: j4c9d2e71a03
Revises: f9518421be39
Create Date: 2026-03-01

This migration adds support for the project import confirmation workflow:
- detected_at: When the project was first detected
- imported_at: When the user confirmed import
- Updates sync_status to use new enum values
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j4c9d2e71a03"
down_revision: Union[str, None] = "f9518421be39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.add_column(
        "repositories",
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "repositories",
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Create index on detected_at for efficient querying
    op.create_index(
        "ix_repositories_detected_at",
        "repositories",
        ["detected_at"],
        unique=False
    )

    # Create index on sync_status for filtering
    op.create_index(
        "ix_repositories_sync_status",
        "repositories",
        ["sync_status"],
        unique=False
    )

    # Migrate existing data:
    # - Projects with sync_status="SYNCED" or "PENDING_CREATION" are considered imported
    # - Set detected_at = created_at for existing projects
    # - Set imported_at = created_at for already-synced projects
    op.execute("""
        UPDATE repositories
        SET
            detected_at = created_at,
            imported_at = CASE
                WHEN sync_status IN ('SYNCED', 'PENDING_CREATION') THEN created_at
                ELSE NULL
            END
        WHERE detected_at IS NULL
    """)

    # Note: We keep existing sync_status values:
    # - "SYNCED" -> stays SYNCED (already imported and synced)
    # - "PENDING_CREATION" -> stays PENDING_CREATION (imported but not yet synced)
    # - "DISCONNECTED" -> stays DISCONNECTED (directory deleted)
    # New projects will use "DETECTED" (new default in model)


def downgrade() -> None:
    # Remove indexes
    op.drop_index("ix_repositories_sync_status", table_name="repositories")
    op.drop_index("ix_repositories_detected_at", table_name="repositories")

    # Remove columns
    op.drop_column("repositories", "imported_at")
    op.drop_column("repositories", "detected_at")

    # Note: We don't revert sync_status values, as the old code
    # should still work with the new enum values
