"""add server-side DEFAULT values to agent_activities NOT NULL columns

The original DDL created all non-nullable columns without server-side DEFAULT
clauses.  SQLAlchemy's ``default=`` parameter is Python-only, so a raw INSERT
(or a partial ORM insert) that omits a column would trigger a NOT NULL
violation from PostgreSQL.

This migration adds DEFAULT values at the DB level to match the ORM model:
  status               DEFAULT 'idle'
  main_goal            DEFAULT ''
  artifacts_json       DEFAULT '[]'
  agent_state_json     DEFAULT '{}'
  active_memories_json DEFAULT '[]'
  final_outcome        DEFAULT ''
  updated_at           DEFAULT now()

Revision ID: 25e4171f16ba
Revises: 281a2571267c
Create Date: 2026-05-31 09:17:03.190061

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '25e4171f16ba'
down_revision = '281a2571267c'
branch_labels = None
depends_on = None


COLUMNS_WITH_DEFAULTS = [
    ('status', sa.VARCHAR(50), 'idle'),
    ('main_goal', sa.Text(), ''),
    ('artifacts_json', sa.Text(), '[]'),
    ('agent_state_json', sa.Text(), '{}'),
    ('active_memories_json', sa.Text(), '[]'),
    ('final_outcome', sa.Text(), ''),
    ('updated_at', sa.TIMESTAMP(timezone=True), sa.text('now()')),
]


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        for col, col_type, default in COLUMNS_WITH_DEFAULTS:
            op.alter_column(
                'agent_activities', col,
                existing_type=col_type,
                existing_nullable=False,
                server_default=default,
            )
        return
    with op.batch_alter_table('agent_activities') as batch_op:
        for col, col_type, default in COLUMNS_WITH_DEFAULTS:
            batch_op.alter_column(
                col,
                existing_type=col_type,
                existing_nullable=False,
                server_default=default,
            )


def downgrade():
    # Remove the server-side defaults, reverting to the original bare NOT NULL state.
    if op.get_bind().dialect.name == "postgresql":
        for col, _, _ in COLUMNS_WITH_DEFAULTS:
            op.alter_column('agent_activities', col, server_default=None)
        return
    with op.batch_alter_table('agent_activities') as batch_op:
        for col, col_type, _ in COLUMNS_WITH_DEFAULTS:
            batch_op.alter_column(col, existing_type=col_type, existing_nullable=False, server_default=None)
