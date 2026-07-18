"""add_codechunk_semantic_flags_coderelation_confidence_security_findings_app_map_route_links

Revision ID: d1e9b2a3c4f5
Revises: c3471a6ff31a
Create Date: 2026-07-17 05:00:00.000000

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "d1e9b2a3c4f5"
down_revision = "c3471a6ff31a"
branch_labels = None
depends_on = None


def upgrade():
    # Add security_scan_status to source_files
    op.add_column(
        "source_files",
        sa.Column("security_scan_status", sa.String(length=20), nullable=False, server_default="pending"),
    )

    # Add semantic flags to code_chunks
    op.add_column(
        "code_chunks",
        sa.Column("is_api_route", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "code_chunks",
        sa.Column("api_method", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "code_chunks",
        sa.Column("api_path", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "code_chunks",
        sa.Column("is_db_model", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "code_chunks",
        sa.Column("db_table_name", sa.String(length=100), nullable=True),
    )

    # Add confidence to code_relations
    op.add_column(
        "code_relations",
        sa.Column("confidence", sa.String(length=20), nullable=False, server_default="EXTRACTED"),
    )

    # Create security_findings table
    op.create_table(
        "security_findings",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("source_file_id", sa.Integer(), nullable=False),
        sa.Column("finding_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("code_snippet", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["source_file_id"], ["source_files.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_security_findings_source_file_id", "security_findings", ["source_file_id"])
    op.create_index("ix_security_findings_finding_type", "security_findings", ["finding_type"])
    op.create_index("ix_security_findings_severity", "security_findings", ["severity"])

    # Create app_map_route_links table
    op.create_table(
        "app_map_route_links",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("app_map_id", sa.Integer(), nullable=False),
        sa.Column("code_chunk_id", sa.Integer(), nullable=True),
        sa.Column("relation_kind", sa.String(length=20), nullable=False),
        sa.Column("logical_path", sa.String(length=512), nullable=True),
        sa.Column("logical_method", sa.String(length=10), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["app_map_id"], ["app_maps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["code_chunk_id"], ["code_chunks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_app_map_route_links_app_map_id", "app_map_route_links", ["app_map_id"])
    op.create_index("ix_app_map_route_links_code_chunk_id", "app_map_route_links", ["code_chunk_id"])


def downgrade():
    op.drop_index("ix_app_map_route_links_code_chunk_id", table_name="app_map_route_links")
    op.drop_index("ix_app_map_route_links_app_map_id", table_name="app_map_route_links")
    op.drop_table("app_map_route_links")

    op.drop_index("ix_security_findings_severity", table_name="security_findings")
    op.drop_index("ix_security_findings_finding_type", table_name="security_findings")
    op.drop_index("ix_security_findings_source_file_id", table_name="security_findings")
    op.drop_table("security_findings")

    op.drop_column("code_relations", "confidence")

    op.drop_column("code_chunks", "db_table_name")
    op.drop_column("code_chunks", "is_db_model")
    op.drop_column("code_chunks", "api_path")
    op.drop_column("code_chunks", "api_method")
    op.drop_column("code_chunks", "is_api_route")

    op.drop_column("source_files", "security_scan_status")
