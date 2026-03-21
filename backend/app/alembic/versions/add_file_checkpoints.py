"""Add file checkpoints

Revision ID: add_file_checkpoints
Revises: 
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_file_checkpoints'
down_revision = None  # Update this to point to your last migration
branch_labels = None
depends_on = None


def upgrade():
    # Create file_checkpoints table
    op.create_table(
        'file_checkpoints',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('thread_id', sa.String(length=255), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.String(length=20), nullable=False, server_default='manual'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('source_message_id', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_file_checkpoints_thread_id', 'file_checkpoints', ['thread_id'])
    op.create_index('ix_file_checkpoints_project_id', 'file_checkpoints', ['project_id'])
    op.create_index('ix_file_checkpoints_thread_created', 'file_checkpoints', ['thread_id', 'created_at'])
    
    # Create file_checkpoint_snapshots table
    op.create_table(
        'file_checkpoint_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('checkpoint_id', sa.Integer(), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('line_count', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['checkpoint_id'], ['file_checkpoints.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('checkpoint_id', 'file_path', name='ix_file_checkpoint_snapshots_unique')
    )
    
    # Create index on checkpoint_id for faster lookups
    op.create_index('ix_file_checkpoint_snapshots_checkpoint_id', 'file_checkpoint_snapshots', ['checkpoint_id'])


def downgrade():
    op.drop_index('ix_file_checkpoint_snapshots_checkpoint_id', table_name='file_checkpoint_snapshots')
    op.drop_table('file_checkpoint_snapshots')
    
    op.drop_index('ix_file_checkpoints_thread_created', table_name='file_checkpoints')
    op.drop_index('ix_file_checkpoints_project_id', table_name='file_checkpoints')
    op.drop_index('ix_file_checkpoints_thread_id', table_name='file_checkpoints')
    op.drop_table('file_checkpoints')
