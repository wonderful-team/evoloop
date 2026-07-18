"""merge_heads

Revision ID: c3471a6ff31a
Revises: 00f8f4256d53, 366c99c58d20
Create Date: 2026-07-17 05:07:48.880289

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'c3471a6ff31a'
down_revision = ('00f8f4256d53', '366c99c58d20')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
