"""Merge indexing status and project requirement branches

Revision ID: 486bc0806e06
Revises: c3397314c4e7, k5d1e3f82b14
Create Date: 2026-03-03 15:01:52.508243

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '486bc0806e06'
down_revision = ('c3397314c4e7', 'k5d1e3f82b14')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
