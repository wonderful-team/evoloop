"""add atlas tables (atlas_apps, atlas_states, atlas_transitions)

Revision ID: 1569b5fdd982
Revises: bf884177c272
Create Date: 2026-06-24 00:47:45.340617

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "1569b5fdd982"
down_revision = "bf884177c272"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "atlas_apps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bundle_id", sa.String(255), nullable=False),
        sa.Column("app_name", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False, server_default="macos"),
        sa.Column("version_hash", sa.String(64), nullable=True),
        sa.Column(
            "last_observed_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id"),
    )
    op.create_index("ix_atlas_apps_bundle_id", "atlas_apps", ["bundle_id"])

    op.create_table(
        "atlas_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("state_id", sa.String(255), nullable=False),
        sa.Column("window_title", sa.String(512), nullable=False, server_default=""),
        sa.Column("screenshot_hash", sa.String(64), nullable=True),
        sa.Column("elements_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["app_id"], ["atlas_apps.id"], name="fk_atlas_states_app_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "atlas_transitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("from_state_id", sa.String(255), nullable=False),
        sa.Column("to_state_id", sa.String(255), nullable=False),
        sa.Column("action_label", sa.String(255), nullable=False, server_default=""),
        sa.Column("action_type", sa.String(50), nullable=False, server_default="click"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["app_id"], ["atlas_apps.id"], name="fk_atlas_transitions_app_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("atlas_transitions")
    op.drop_table("atlas_states")
    op.drop_table("atlas_apps")
