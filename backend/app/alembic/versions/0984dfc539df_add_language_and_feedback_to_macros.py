"""add feedback to macros

Revision ID: 0984dfc539df
Revises: da11f0635fe3
Create Date: 2026-08-01 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '0984dfc539df'
down_revision = 'da11f0635fe3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'macros',
        sa.Column('feedback', sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_column('macros', 'feedback')
