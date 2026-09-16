"""add member_id columns

Revision ID: b57b82ccfaac
Revises: cb2eace845a1
Create Date: 2026-05-25 05:20:41.395686

"""
import sqlalchemy as sa
from alembic import op

revision = "b57b82ccfaac"
down_revision = "cb2eace845a1"
branch_labels = None
depends_on = None

TABLES = [
    "autonomous_tasks",
    "conversations",
    "learned_skills",
    "memory_concepts",
    "messages",
    "project_resources",
    "project_tasks",
    "repositories",
    "synthesis_jobs",
    "todos",
    "trace_events",
    "wikipage",
]

def upgrade():
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    for table in TABLES:
        if is_postgres:
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS member_id INTEGER NOT NULL DEFAULT 0")
        else:
            columns = {c["name"] for c in sa.inspect(bind).get_columns(table)}
            if "member_id" not in columns:
                op.add_column(table, sa.Column("member_id", sa.Integer(), nullable=False, server_default="0"))
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_member_id ON {table} (member_id)")

def downgrade():
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    for table in reversed(TABLES):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_member_id")
        if is_postgres:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS member_id")
        else:
            columns = {c["name"] for c in sa.inspect(bind).get_columns(table)}
            if "member_id" in columns:
                op.drop_column(table, "member_id")
