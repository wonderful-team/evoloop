"""add_memory_index

Revision ID: ebc64340ba7d
Revises: 25e4171f16ba
Create Date: 2026-06-13 02:02:34.862513

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'ebc64340ba7d'
down_revision = '25e4171f16ba'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'memory_index',
        sa.Column('id', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('tier', sa.String(length=50), nullable=False),
        sa.Column('privacy', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('member_id', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('source', sa.String(length=100), nullable=True),
        
        sa.Column('source_file_path', sa.Text(), nullable=True),
        sa.Column('source_thread_id', sa.String(length=255), nullable=True),
        sa.Column('source_message_id', sa.String(length=255), nullable=True),
        sa.Column('source_run_id', sa.String(length=255), nullable=True),
        sa.Column('source_wiki_title', sa.String(length=255), nullable=True),
        
        sa.Column('content_hash', sa.String(length=255), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('utility_score', sa.Float(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=True, server_default='1'),
        
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_memory_index_type', 'memory_index', ['type'], unique=False)
    op.create_index('ix_memory_index_project_id', 'memory_index', ['project_id'], unique=False)
    op.create_index('ix_memory_index_member_id', 'memory_index', ['member_id'], unique=False)
    op.create_index('ix_memory_index_source_thread_id', 'memory_index', ['source_thread_id'], unique=False)
    op.create_index('ix_memory_index_source_message_id', 'memory_index', ['source_message_id'], unique=False)
    op.create_index('ix_memory_index_source_run_id', 'memory_index', ['source_run_id'], unique=False)
    op.create_index('ix_memory_index_content_hash', 'memory_index', ['content_hash'], unique=False)


def downgrade():
    op.drop_index('ix_memory_index_content_hash', table_name='memory_index')
    op.drop_index('ix_memory_index_source_run_id', table_name='memory_index')
    op.drop_index('ix_memory_index_source_message_id', table_name='memory_index')
    op.drop_index('ix_memory_index_source_thread_id', table_name='memory_index')
    op.drop_index('ix_memory_index_member_id', table_name='memory_index')
    op.drop_index('ix_memory_index_project_id', table_name='memory_index')
    op.drop_index('ix_memory_index_type', table_name='memory_index')
    op.drop_table('memory_index')
