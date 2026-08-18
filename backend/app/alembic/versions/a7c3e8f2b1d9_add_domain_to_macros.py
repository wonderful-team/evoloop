"""add_domain_to_macros

Revision ID: a7c3e8f2b1d9
Revises: 925e1ee5a3d6
Create Date: 2026-08-16 12:00:00.000000

宏注册表新增 domain 字段（业务域声明，§13.2 宏模式）：
业务域清单由宏注册表动态生成（业务接管清单的前端数据源）。
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c3e8f2b1d9"
down_revision = "925e1ee5a3d6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "macros",
        sa.Column("domain", sa.String(length=100), nullable=True),
    )
    op.create_index("ix_macros_domain", "macros", ["domain"], unique=False)


def downgrade():
    op.drop_index("ix_macros_domain", table_name="macros")
    op.drop_column("macros", "domain")
