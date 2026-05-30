"""restore checkpoints jsonb

Revision ID: 5177c2728211
Revises: 91ccf71659ee
Create Date: 2026-05-28 01:09:47.123456

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '5177c2728211'
down_revision = '91ccf71659ee'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('checkpoints', 'checkpoint',
               type_=postgresql.JSONB(astext_type=sa.Text()),
               postgresql_using="checkpoint::jsonb")
    op.alter_column('checkpoints', 'metadata',
               type_=postgresql.JSONB(astext_type=sa.Text()),
               postgresql_using="metadata::jsonb")


def downgrade():
    op.alter_column('checkpoints', 'checkpoint',
               type_=sa.JSON())
    op.alter_column('checkpoints', 'metadata',
               type_=sa.JSON())
