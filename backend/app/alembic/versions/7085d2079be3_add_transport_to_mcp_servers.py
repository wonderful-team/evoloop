"""add transport to mcp_servers

Revision ID: 7085d2079be3
Revises: a3f5c7e9b1d2
Create Date: 2026-09-22 04:35:46.687821

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '7085d2079be3'
down_revision = 'a3f5c7e9b1d2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mcp_servers', sa.Column('transport', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('mcp_servers', 'transport')
