"""add_citation_tables

Revision ID: b7408b54ac53
Revises: a4899aa1a087
Create Date: 2026-04-23 21:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7408b54ac53"
down_revision = "a4899aa1a087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "citations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_id", sa.String(length=1024), nullable=False),
        sa.Column("doc_path", sa.String(length=1024), nullable=False),
        sa.Column("tool_used", sa.String(length=50), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("agent_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_citations_doc_id", "citations", ["doc_id"])
    op.create_index("ix_citations_session_id", "citations", ["session_id"])

    op.create_table(
        "doc_stats",
        sa.Column("doc_id", sa.String(length=1024), nullable=False),
        sa.Column("doc_path", sa.String(length=1024), nullable=False),
        sa.Column("total_citations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tools_used", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("doc_id"),
    )

    op.create_table(
        "session_docs",
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("doc_id", sa.String(length=1024), nullable=False),
        sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "doc_id"),
    )


def downgrade() -> None:
    op.drop_table("session_docs")
    op.drop_table("doc_stats")
    op.drop_index("ix_citations_session_id", table_name="citations")
    op.drop_index("ix_citations_doc_id", table_name="citations")
    op.drop_table("citations")
