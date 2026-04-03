"""add_subtask_support

Revision ID: 20250403_add_subtask_support
Revises: 20250328_add_meta_data_to_message_references
Create Date: 2025-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250403_add_subtask_support'
down_revision: Union[str, None] = '20250328_add_meta_data_to_message_references'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add subtask support to project_requirement_tasks table."""
    
    # Add parent_id for hierarchical structure
    op.add_column(
        'project_requirement_tasks',
        sa.Column('parent_id', sa.String(36), nullable=True)
    )
    
    # Add index on parent_id for efficient tree queries
    op.create_index(
        'ix_project_requirement_tasks_parent_id',
        'project_requirement_tasks',
        ['parent_id']
    )
    
    # Add foreign key constraint (self-referencing)
    op.create_foreign_key(
        'fk_project_requirement_tasks_parent',
        'project_requirement_tasks',
        'project_requirement_tasks',
        ['parent_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Add status field for task execution tracking
    op.add_column(
        'project_requirement_tasks',
        sa.Column('status', sa.String(50), nullable=False, server_default='pending')
    )
    
    # Add index on status for filtering
    op.create_index(
        'ix_project_requirement_tasks_status',
        'project_requirement_tasks',
        ['status']
    )
    
    # Add progress field (0-100)
    op.add_column(
        'project_requirement_tasks',
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0')
    )
    
    # Add updated_at field
    op.add_column(
        'project_requirement_tasks',
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Add composite index for project + status queries
    op.create_index(
        'ix_project_requirement_tasks_project_status',
        'project_requirement_tasks',
        ['project_id', 'status']
    )
    
    # Add index for root tasks (parent_id is NULL)
    op.execute("""
        CREATE INDEX ix_project_requirement_tasks_root 
        ON project_requirement_tasks (project_id) 
        WHERE parent_id IS NULL
    """)


def downgrade() -> None:
    """Remove subtask support."""
    
    # Drop indexes
    op.drop_index('ix_project_requirement_tasks_root', table_name='project_requirement_tasks')
    op.drop_index('ix_project_requirement_tasks_project_status', table_name='project_requirement_tasks')
    op.drop_index('ix_project_requirement_tasks_status', table_name='project_requirement_tasks')
    op.drop_index('ix_project_requirement_tasks_parent_id', table_name='project_requirement_tasks')
    
    # Drop foreign key
    op.drop_constraint('fk_project_requirement_tasks_parent', 'project_requirement_tasks', type_='foreignkey')
    
    # Drop columns
    op.drop_column('project_requirement_tasks', 'updated_at')
    op.drop_column('project_requirement_tasks', 'progress')
    op.drop_column('project_requirement_tasks', 'status')
    op.drop_column('project_requirement_tasks', 'parent_id')
