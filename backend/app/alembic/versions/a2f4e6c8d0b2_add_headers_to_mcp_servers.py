"""add headers to mcp_servers

Revision ID: a2f4e6c8d0b2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-02 10:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a2f4e6c8d0b2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 给 mcp_servers 增加 headers 列（JSON 字符串），用于 SSE transport 的认证/自定义 Header
    op.add_column("mcp_servers", sa.Column("headers", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("mcp_servers", "headers")
