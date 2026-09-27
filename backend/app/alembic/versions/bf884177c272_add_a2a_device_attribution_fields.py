"""add_a2a_device_attribution_fields

Revision ID: bf884177c272
Revises: 916cca005041
Create Date: 2026-06-20 18:12:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'bf884177c272'
down_revision = '916cca005041'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add columns to conversations table
    op.add_column('conversations', sa.Column('caller_device_key', sa.String(length=255), nullable=True))
    op.add_column('conversations', sa.Column('executor_device_key', sa.String(length=255), nullable=True))
    op.add_column('conversations', sa.Column('executor_device_name', sa.String(length=255), nullable=True))
    
    # 2. Add columns to messages table
    op.add_column('messages', sa.Column('executor_device_key', sa.String(length=255), nullable=True))
    op.add_column('messages', sa.Column('executor_device_name', sa.String(length=255), nullable=True))


def downgrade():
    # 1. Drop columns from messages table
    op.drop_column('messages', 'executor_device_name')
    op.drop_column('messages', 'executor_device_key')
    
    # 2. Drop columns from conversations table
    op.drop_column('conversations', 'executor_device_name')
    op.drop_column('conversations', 'executor_device_key')
    op.drop_column('conversations', 'caller_device_key')
