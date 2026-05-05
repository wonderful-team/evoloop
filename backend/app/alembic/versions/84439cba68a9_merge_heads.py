"""merge heads

Revision ID: 84439cba68a9
Revises: d20259754ee4, dc2cdfff0866
Create Date: 2026-05-03 14:55:39.362654

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '84439cba68a9'
down_revision = ('d20259754ee4', 'dc2cdfff0866')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
