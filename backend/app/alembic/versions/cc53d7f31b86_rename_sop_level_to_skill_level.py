"""rename_sop_level_to_skill_level

Revision ID: cc53d7f31b86
Revises: bb42b0e55725
Create Date: 2026-02-20 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cc53d7f31b86'
down_revision = 'bb42b0e55725'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename sop_level to skill_level in learned_skills table
    op.alter_column('learned_skills', 'sop_level', new_column_name='skill_level')


def downgrade() -> None:
    # Rename skill_level back to sop_level
    op.alter_column('learned_skills', 'skill_level', new_column_name='sop_level')
