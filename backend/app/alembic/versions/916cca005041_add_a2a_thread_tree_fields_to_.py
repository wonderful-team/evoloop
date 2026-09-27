"""add_a2a_thread_tree_fields_to_conversation

Revision ID: 916cca005041
Revises: 2348a4eedb27
Create Date: 2026-06-19 21:09:23.921462

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '916cca005041'
down_revision = '2348a4eedb27'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('conversations', sa.Column('root_thread_id', sa.String(length=255), nullable=True))
    op.add_column('conversations', sa.Column('parent_thread_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_conversations_parent_thread_id'), 'conversations', ['parent_thread_id'], unique=False)
    op.create_index(op.f('ix_conversations_root_thread_id'), 'conversations', ['root_thread_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_conversations_root_thread_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_parent_thread_id'), table_name='conversations')
    op.drop_column('conversations', 'parent_thread_id')
    op.drop_column('conversations', 'root_thread_id')
