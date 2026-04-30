"""
Drop agent_activities.steps_json column

Revision ID: d20259754ee4
Revises: p1q2r3s4t5u6
Create Date: 2026-04-30 17:00:00
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd20259754ee4'
down_revision = 'p1q2r3s4t5u6'
branch_labels = None
depends_on = None


def upgrade():
    """
    Drop steps_json column from agent_activities table.

    Phase 3 of real-time/historical link unification:
    Step state is now stored in the Message table (role="tool") and
    reconstructed on-demand by ActivityStateService.get_state().
    The legacy steps_json field is no longer read or written.
    """
    op.drop_column('agent_activities', 'steps_json')


def downgrade():
    """
    Re-add steps_json column to agent_activities table.
    """
    op.add_column(
        'agent_activities',
        sa.Column('steps_json', sa.Text(), nullable=False, server_default='[]')
    )
