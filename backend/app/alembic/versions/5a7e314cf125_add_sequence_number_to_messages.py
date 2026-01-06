"""add_sequence_number_to_messages

Revision ID: 5a7e314cf125
Revises: 3f056ac57cf4
Create Date: 2026-01-06 00:43:08.492568

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5a7e314cf125'
down_revision = '3f056ac57cf4'
branch_labels = None
depends_on = None


def upgrade():
    # Add sequence_number column to messages table
    op.add_column('messages', sa.Column('sequence_number', sa.Integer(), nullable=True))


def downgrade():
    # Remove sequence_number column
    op.drop_column('messages', 'sequence_number')
