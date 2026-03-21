"""
Normalize message roles to standard values

Revision ID: n8o9p0q1r2s3
Revises: m6n7o8p9q0r1_add_file_checkpoints
Create Date: 2026-03-21 14:30:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'n8o9p0q1r2s3'
down_revision = 'm6n7o8p9q0r1_add_file_checkpoints'
branch_labels = None
depends_on = None


def upgrade():
    """
    Normalize role values:
    - "user" -> "human"
    - "assistant" -> "ai"
    """
    # Update "user" to "human"
    op.execute("UPDATE messages SET role = 'human' WHERE role = 'user'")
    
    # Update "assistant" to "ai"
    op.execute("UPDATE messages SET role = 'ai' WHERE role = 'assistant'")
    
    print("✓ Normalized message roles: user->human, assistant->ai")


def downgrade():
    """
    Restore old role values (if needed for rollback).
    """
    # Restore "ai" to "assistant"
    op.execute("UPDATE messages SET role = 'assistant' WHERE role = 'ai'")
    
    # Restore "human" to "user"
    op.execute("UPDATE messages SET role = 'user' WHERE role = 'human'")
    
    print("✓ Restored old message roles: human->user, ai->assistant")
