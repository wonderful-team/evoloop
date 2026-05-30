"""add node_source to messages

Revision ID: 91ccf71659ee
Revises: b57b82ccfaac
Create Date: 2026-05-28 01:08:02.739990

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '91ccf71659ee'
down_revision = 'b57b82ccfaac'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('messages', sa.Column('node_source', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_messages_node_source'), 'messages', ['node_source'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_messages_node_source'), table_name='messages')
    op.drop_column('messages', 'node_source')
