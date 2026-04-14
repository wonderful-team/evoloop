"""add_thread_sequence_index_to_messages

Revision ID: bb93c448ec99
Revises: fb41d2deedf2
Create Date: 2026-03-21 15:30:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'bb93c448ec99'
down_revision = 'fb41d2deedf2'
branch_labels = None
depends_on = None


def upgrade():
    # Add composite index for efficient thread message retrieval with ordering
    # This optimizes the primary query pattern in get_conversation_messages():
    # SELECT * FROM messages WHERE thread_id = ? ORDER BY sequence_number ASC
    op.create_index(
        'ix_messages_thread_sequence',
        'messages',
        ['thread_id', 'sequence_number'],
        unique=False
    )
    
    # Also add index for parent_id lookups (threading support)
    op.create_index(
        'ix_messages_parent_id',
        'messages',
        ['parent_id'],
        unique=False
    )


def downgrade():
    op.drop_index('ix_messages_parent_id', table_name='messages')
    op.drop_index('ix_messages_thread_sequence', table_name='messages')
