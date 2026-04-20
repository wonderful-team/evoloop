"""cleanup_multiple_heads

Revision ID: 878f1f175b93
Revises: 20250321_macro_script_yaml, 20250328_add_metadata, 20250403_add_subtask_support, 20260407_add_message_category, bb93c448ec99, bf5bc9eccf8c, p1q2r3s4t5u6
Create Date: 2026-04-20 02:22:55.416505

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '878f1f175b93'
down_revision = ('20250321_macro_script_yaml', '20250328_add_metadata', '20250403_add_subtask_support', '20260407_add_message_category', 'bb93c448ec99', 'bf5bc9eccf8c', 'p1q2r3s4t5u6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
