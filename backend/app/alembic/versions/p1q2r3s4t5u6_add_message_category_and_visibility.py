"""
Add message category and visibility columns

Revision ID: p1q2r3s4t5u6
Revises: n8o9p0q1r2s3_normalize_message_roles
Create Date: 2026-04-06 11:00:00
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'p1q2r3s4t5u6'
down_revision = 'n8o9p0q1r2s3_normalize_message_roles'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add category and is_visible columns to messages table.
    
    These columns support the unified message classification system:
    - category: MessageCategory enum value (user, assistant_response, error_system, etc.)
    - is_visible: Whether the message should be shown in the conversation UI
    """
    # Add category column
    op.add_column(
        'messages',
        sa.Column('category', sa.String(50), nullable=True, index=True)
    )
    
    # Add is_visible column with default True
    op.add_column(
        'messages',
        sa.Column('is_visible', sa.Boolean(), nullable=True, server_default='1')
    )
    
    # Update existing rows to have default values
    op.execute("UPDATE messages SET category = 'user' WHERE role = 'human'")
    op.execute("UPDATE messages SET category = 'assistant_response' WHERE role = 'ai'")
    op.execute("UPDATE messages SET is_visible = 1 WHERE is_visible IS NULL")
    
    print("✓ Added category and is_visible columns to messages table")


def downgrade():
    """
    Remove category and is_visible columns.
    """
    op.drop_column('messages', 'is_visible')
    op.drop_column('messages', 'category')
    
    print("✓ Removed category and is_visible columns from messages table")
