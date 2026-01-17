"""Add learned_skills table

Revision ID: g9d3b5f20c84
Revises: f8c2a4e19b73
Create Date: 2026-01-06 13:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g9d3b5f20c84'
down_revision: Union[str, None] = 'f8c2a4e19b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # op.create_table(
    #     'learned_skills',
    #     sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
    #     sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
    #     sa.Column('description', sa.Text(), nullable=False),
    #     sa.Column('trigger_patterns', sa.Text(), nullable=False),
    #     sa.Column('parameters', sa.Text(), nullable=False),
    #     sa.Column('preconditions', sa.Text(), nullable=True),
    #     sa.Column('steps', sa.Text(), nullable=False),
    #     sa.Column('tools_used', sa.Text(), nullable=True),
    #     sa.Column('source_thread_id', sa.String(255), nullable=True),
    #     sa.Column('source_session_id', sa.String(255), nullable=True),
    #     sa.Column('success_count', sa.Integer(), nullable=False, server_default='0'),
    #     sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
    #     sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
    #     sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    #     sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    # )
    pass


def downgrade() -> None:
    op.drop_table('learned_skills')
