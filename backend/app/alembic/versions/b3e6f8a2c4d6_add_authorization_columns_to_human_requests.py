"""add authorization columns to human_requests

终态 HITL 授权模型（v2）：
- resource_path / resource_action：授权门控的机器可读资源锚点，
  拒绝判死与近期放行查询只认这两列（归一化绝对路径），
  替代历史 description 文本子串匹配（contains/endswith）。
- expires_at：判死/授权的自然过期时间，拒绝 TTL 到期后允许再次发起审批。

Revision ID: b3e6f8a2c4d6
Revises: 7085d2079be3
Create Date: 2026-09-22 09:45:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b3e6f8a2c4d0"
down_revision = "7085d2079be3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "human_requests",
        sa.Column("resource_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "human_requests",
        sa.Column("resource_action", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "human_requests",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_human_requests_thread_resource",
        "human_requests",
        ["thread_id", "resource_path"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_human_requests_thread_resource", table_name="human_requests")
    op.drop_column("human_requests", "expires_at")
    op.drop_column("human_requests", "resource_action")
    op.drop_column("human_requests", "resource_path")
