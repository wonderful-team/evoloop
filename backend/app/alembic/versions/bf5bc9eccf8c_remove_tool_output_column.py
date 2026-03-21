"""
Remove deprecated tool_output column from messages

Revision ID: bf5bc9eccf8c
Revises: m6n7o8p9q0r1
Create Date: 2026-03-21 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bf5bc9eccf8c'
down_revision = 'm6n7o8p9q0r1'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the deprecated tool_output column
    # Data has been migrated to content column with action_type='tool_output'
    op.drop_column('messages', 'tool_output')


def downgrade():
    # Recreate the tool_output column (for rollback only)
    op.add_column(
        'messages',
        sa.Column('tool_output', sa.Text(), nullable=True)
    )
