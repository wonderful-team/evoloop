"""rename_message_tasks_to_steps

Revision ID: f1ace84be29a
Revises: e337d1506393
Create Date: 2026-01-19 21:21:53.303661

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f1ace84be29a'
down_revision = 'e337d1506393'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('messages', 'tasks_snapshot', new_column_name='steps_snapshot')


def downgrade() -> None:
    op.alter_column('messages', 'steps_snapshot', new_column_name='tasks_snapshot')
