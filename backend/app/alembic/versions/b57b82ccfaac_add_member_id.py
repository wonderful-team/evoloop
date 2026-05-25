"""add member_id columns

Revision ID: b57b82ccfaac
Revises: cb2eace845a1
Create Date: 2026-05-25 05:20:41.395686

"""
from alembic import op
import sqlalchemy as sa

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
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS member_id INTEGER NOT NULL DEFAULT 0")
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_member_id ON {table} (member_id)")

def downgrade():
    for table in reversed(TABLES):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_member_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS member_id")
