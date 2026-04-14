"""Add metadata column to message_references

Revision ID: 20250328_add_metadata
Revises: 302db0c0ccdd
Create Date: 2025-03-28 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '20250328_add_metadata'
down_revision = '302db0c0ccdd'
branch_labels = None
depends_on = None


def upgrade():
    # Add metadata column to message_references table
    op.add_column('message_references', sa.Column('metadata', sa.JSON(), nullable=True))


def downgrade():
    # Remove metadata column
    op.drop_column('message_references', 'metadata')
