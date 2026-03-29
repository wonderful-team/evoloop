"""Add meta_data to message_references

Revision ID: 20250328_add_meta_data
Revises: 
Create Date: 2026-03-28 12:40:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250328_add_meta_data'
down_revision = 'n8o9p0q1r2s3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add meta_data column to message_references table
    op.add_column('message_references', sa.Column('meta_data', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Drop meta_data column
    op.drop_column('message_references', 'meta_data')
