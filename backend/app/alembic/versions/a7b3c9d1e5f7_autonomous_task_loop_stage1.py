"""autonomous task loop stage 1: queue fields on project_tasks + plan.task_id

Revision ID: a7b3c9d1e5f7
Revises: c8d2e4f6a8b0
Create Date: 2026-09-12

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a7b3c9d1e5f7'
down_revision = 'c8d2e4f6a8b0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('project_tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=20), nullable=False, server_default='user'))
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('type', sa.String(length=20), nullable=False, server_default='once'))
        batch_op.add_column(sa.Column('source_ref', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('dedup_key', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('risk_level', sa.String(length=4), nullable=True))
        batch_op.add_column(sa.Column('due_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('trigger_spec', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('self_check', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('acceptance', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('last_thread_id', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_project_tasks_source', ['source'])
        batch_op.create_index('ix_project_tasks_dedup_key', ['dedup_key'], unique=True)
        batch_op.create_index('ix_project_tasks_due_at', ['due_at'])
        batch_op.create_index('ix_project_tasks_next_run_at', ['next_run_at'])

    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_plans_task_id_project_tasks',
            'project_tasks',
            ['task_id'],
            ['id'],
        )
        batch_op.create_index('ix_plans_task_id', ['task_id'])


def downgrade():
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.drop_index('ix_plans_task_id')
        batch_op.drop_constraint('fk_plans_task_id_project_tasks', type_='foreignkey')
        batch_op.drop_column('task_id')

    with op.batch_alter_table('project_tasks', schema=None) as batch_op:
        batch_op.drop_index('ix_project_tasks_next_run_at')
        batch_op.drop_index('ix_project_tasks_due_at')
        batch_op.drop_index('ix_project_tasks_dedup_key')
        batch_op.drop_index('ix_project_tasks_source')
        batch_op.drop_column('last_thread_id')
        batch_op.drop_column('acceptance')
        batch_op.drop_column('self_check')
        batch_op.drop_column('next_run_at')
        batch_op.drop_column('trigger_spec')
        batch_op.drop_column('due_at')
        batch_op.drop_column('risk_level')
        batch_op.drop_column('dedup_key')
        batch_op.drop_column('source_ref')
        batch_op.drop_column('type')
        batch_op.drop_column('description')
        batch_op.drop_column('source')
