"""add capability json to learned_skills

Revision ID: c8d2e4f6a8b0
Revises: 7c9a0b1d2e3f
Create Date: 2026-09-11

能力包声明列（capability-packages-refactor.md §5.1）：
{domain, tools: [{mcp_server, include?}], preload, route_patterns}
null = 普通技能。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c8d2e4f6a8b0"
down_revision = "7c9a0b1d2e3f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("learned_skills", schema=None) as batch_op:
        batch_op.add_column(sa.Column("capability", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("learned_skills", schema=None) as batch_op:
        batch_op.drop_column("learned_skills", "capability")
