"""add_updated_at_to_messages

Revision ID: 7a2b3c4d5e6f
Revises: 6cf8dace5e0e
Create Date: 2026-04-27 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7a2b3c4d5e6f'
down_revision = '6cf8dace5e0e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('messages', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('messages', 'updated_at')
