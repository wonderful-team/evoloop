"""drop KB citation tables

Revision ID: 6a314534fcc4
Revises: b3a226f9fb81
Create Date: 2026-07-06

Drop the citation/doc_stats/session_docs tables that belonged to the
removed Document Knowledge Base feature. The KB domain layer, routes,
models, and tools have been deleted; these tables are now orphaned.
"""
from alembic import op

revision = "6a314534fcc4"
down_revision = "b3a226f9fb81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS citations CASCADE")
    op.execute("DROP TABLE IF EXISTS doc_stats CASCADE")
    op.execute("DROP TABLE IF EXISTS session_docs CASCADE")


def downgrade() -> None:
    pass
