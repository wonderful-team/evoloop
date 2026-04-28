"""add_content_type_to_messages

Revision ID: 6cf8dace5e0e
Revises: 42f7ec7e40d5
Create Date: 2026-04-27 15:50:54.889734

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '6cf8dace5e0e'
down_revision = '42f7ec7e40d5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('messages', sa.Column('content_type', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('messages', 'content_type')
