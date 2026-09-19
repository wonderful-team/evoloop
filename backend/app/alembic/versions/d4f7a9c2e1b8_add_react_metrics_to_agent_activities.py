"""add_react_metrics_to_agent_activities

Revision ID: d4f7a9c2e1b8
Revises: f5c8a2d1e9b4
Create Date: 2026-08-30 18:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d4f7a9c2e1b8"
down_revision = "f5c8a2d1e9b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_activities",
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_activities",
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_activities",
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_activities",
        sa.Column("tool_errors", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("agent_activities", "tool_errors")
    op.drop_column("agent_activities", "output_tokens")
    op.drop_column("agent_activities", "input_tokens")
    op.drop_column("agent_activities", "llm_calls")
