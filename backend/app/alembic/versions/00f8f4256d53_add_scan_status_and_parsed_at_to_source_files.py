"""add scan_status and parsed_at to source_files

Revision ID: 00f8f4256d53
Revises: f5c8a2d1e9b4
Create Date: 2026-07-17 12:00:00.000000

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = '00f8f4256d53'
down_revision = 'f5c8a2d1e9b4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'source_files',
        sa.Column('scan_status', sa.String(length=20), nullable=False, server_default='pending'),
    )
    op.add_column(
        'source_files',
        sa.Column('parsed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column('source_files', 'parsed_at')
    op.drop_column('source_files', 'scan_status')
