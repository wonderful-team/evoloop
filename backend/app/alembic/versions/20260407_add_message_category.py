"""
Add message category field

Revision ID: 20260407_add_message_category
Revises: 
Create Date: 2026-04-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260407_add_message_category'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade: Add category column to messages table
    """
    # Add category column
    op.add_column(
        'messages',
        sa.Column(
            'category',
            sa.String(length=50),
            nullable=True,
            index=True,
            comment='Message category for unified lifecycle management: user, assistant_response, assistant_tool_call, tool_output, internal_tool_call, internal_reasoning, internal_system, internal_llm_json'
        )
    )
    
    # Create index for category field (for efficient filtering)
    op.create_index(
        'ix_messages_category',
        'messages',
        ['category'],
        unique=False
    )


def downgrade() -> None:
    """
    Downgrade: Remove category column from messages table
    """
    # Drop index first
    op.drop_index('ix_messages_category', table_name='messages')
    
    # Drop column
    op.drop_column('messages', 'category')
