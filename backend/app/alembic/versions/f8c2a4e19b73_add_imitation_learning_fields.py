"""Add imitation learning fields to trace_events

Revision ID: f8c2a4e19b73
Revises: 5a7e314cf125
Create Date: 2026-01-06 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f8c2a4e19b73'
down_revision: Union[str, None] = '5a7e314cf125'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns for imitation learning
    # op.add_column('trace_events', sa.Column('is_human_action', sa.Boolean(), nullable=False, server_default='false'))
    # op.add_column('trace_events', sa.Column('action_correction', sa.Text(), nullable=True))
    # op.add_column('trace_events', sa.Column('human_feedback', sa.Text(), nullable=True))
    pass
    # op.add_column('trace_events', sa.Column('user_feedback', sa.Text(), nullable=True))
    # op.add_column('trace_events', sa.Column('recording_session_id', sa.String(255), nullable=True))
    
    # Add index for recording_session_id for fast session queries
    # op.create_index(op.f('ix_trace_events_recording_session_id'), 'trace_events', ['recording_session_id'], unique=False)
    pass


def downgrade() -> None:
    op.drop_index(op.f('ix_trace_events_recording_session_id'), table_name='trace_events')
    op.drop_column('trace_events', 'recording_session_id')
    op.drop_column('trace_events', 'user_feedback')
    op.drop_column('trace_events', 'ui_element_info')
    op.drop_column('trace_events', 'screenshot_path')
    op.drop_column('trace_events', 'is_human_action')
