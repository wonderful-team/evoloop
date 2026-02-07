"""Add SOP confidence and status fields

Revision ID: h2a7b8c31d95
Revises: g9d3b5f20c84
Create Date: 2026-02-07 23:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h2a7b8c31d95'
down_revision = 'b33fa95eeae4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add confidence_score and status fields to learned_skills table."""
    # Add confidence_score column with default 0.0
    op.add_column(
        'learned_skills',
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='0.0')
    )
    
    # Add status column with default 'draft'
    op.add_column(
        'learned_skills',
        sa.Column('status', sa.String(20), nullable=False, server_default='draft')
    )
    
    # Remove server defaults after setting values
    op.alter_column('learned_skills', 'confidence_score', server_default=None)
    op.alter_column('learned_skills', 'status', server_default=None)


def downgrade() -> None:
    """Remove confidence_score and status fields from learned_skills table."""
    op.drop_column('learned_skills', 'status')
    op.drop_column('learned_skills', 'confidence_score')
