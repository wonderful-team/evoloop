"""drop node_source from messages (legacy graph-architecture field)

Single-Agent ReAct 重构后不再有 supervisor/worker/finish 图节点标注，
messages.node_source 已无生产者，删除列与索引。

Revision ID: e6f7a8b9c0d1
Revises: b3a9f1c4e2d8
Create Date: 2026-09-01 18:30:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "b3a9f1c4e2d8"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index(op.f("ix_messages_node_source"), table_name="messages")
    op.drop_column("messages", "node_source")


def downgrade():
    import sqlalchemy as sa

    op.add_column(
        "messages",
        sa.Column("node_source", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_messages_node_source"), "messages", ["node_source"], unique=False
    )
