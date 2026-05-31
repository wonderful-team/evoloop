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
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '25e4171f16ba'
down_revision = '281a2571267c'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'agent_activities', 'status',
        existing_type=sa.VARCHAR(50),
        existing_nullable=False,
        server_default='idle',
    )
    op.alter_column(
        'agent_activities', 'main_goal',
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default='',
    )
    op.alter_column(
        'agent_activities', 'artifacts_json',
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default='[]',
    )
    op.alter_column(
        'agent_activities', 'agent_state_json',
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default='{}',
    )
    op.alter_column(
        'agent_activities', 'active_memories_json',
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default='[]',
    )
    op.alter_column(
        'agent_activities', 'final_outcome',
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default='',
    )
    op.alter_column(
        'agent_activities', 'updated_at',
        existing_type=sa.TIMESTAMP(timezone=True),
        existing_nullable=False,
        server_default=sa.text('now()'),
    )


def downgrade():
    # Remove the server-side defaults, reverting to the original bare NOT NULL state.
    for col in ('status', 'main_goal', 'artifacts_json', 'agent_state_json',
                'active_memories_json', 'final_outcome', 'updated_at'):
        op.alter_column('agent_activities', col, server_default=None)
