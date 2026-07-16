"""add app_maps and macros tables

Revision ID: a1b2c3d4e5f6
Revises: b184728f63c0
Create Date: 2026-07-15 12:00:00.000000

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '7c9a0b1d2e3f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_maps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('entity', sa.String(length=100), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False, server_default='web'),
        sa.Column('aliases', sa.JSON(), nullable=False),
        sa.Column('routes', sa.JSON(), nullable=False),
        sa.Column('actions', sa.JSON(), nullable=False),
        sa.Column('elements', sa.JSON(), nullable=False),
        sa.Column('db_tables', sa.JSON(), nullable=False),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('map_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('generation_thread_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('validation_report', sa.JSON(), nullable=True),
        sa.Column('member_id', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_app_maps_project_id', 'app_maps', ['project_id'])
    op.create_index('ix_app_maps_entity', 'app_maps', ['entity'])
    op.create_index('ix_app_maps_status', 'app_maps', ['status'])
    op.create_index('ix_app_maps_member_id', 'app_maps', ['member_id'])

    op.create_table(
        'macros',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('app_map_id', sa.Integer(), nullable=True),
        sa.Column('entity', sa.String(length=100), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('trigger_patterns', sa.JSON(), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=False),
        sa.Column('macro_script', sa.Text(), nullable=False),
        sa.Column('risk_tier', sa.String(length=10), nullable=False, server_default='ui'),
        sa.Column('requires_confirmation', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending_review'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('namespace', sa.String(length=500), nullable=True),
        sa.Column('fallback_skill_id', sa.Integer(), nullable=True),
        sa.Column('source_thread_id', sa.String(length=255), nullable=True),
        sa.Column('app_map_version', sa.Integer(), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('member_id', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_macros_app_map_id', 'macros', ['app_map_id'])
    op.create_index('ix_macros_entity', 'macros', ['entity'])
    op.create_index('ix_macros_name', 'macros', ['name'])
    op.create_index('ix_macros_status', 'macros', ['status'])
    op.create_index('ix_macros_namespace', 'macros', ['namespace'])
    op.create_index('ix_macros_project_id', 'macros', ['project_id'])
    op.create_index('ix_macros_member_id', 'macros', ['member_id'])


def downgrade():
    op.drop_table('macros')
    op.drop_table('app_maps')
