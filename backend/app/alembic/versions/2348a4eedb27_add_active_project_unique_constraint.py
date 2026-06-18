"""add active project unique constraint

Revision ID: 2348a4eedb27
Revises: 800f1b4d563c
Create Date: 2026-06-19 00:07:28.296837

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "2348a4eedb27"
down_revision = "800f1b4d563c"
branch_labels = None
depends_on = None


def upgrade():
    # Resolve any pre-existing duplicate active project_id rows before adding
    # the unique index. Keep the SYNCED repo if present, otherwise the oldest.
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        op.execute("""
            UPDATE repositories
            SET sync_status = 'DISCONNECTED'
            WHERE id IN (
                SELECT id FROM (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY project_id
                            ORDER BY
                                CASE sync_status WHEN 'SYNCED' THEN 0 ELSE 1 END,
                                id ASC
                        ) AS rn
                    FROM repositories
                    WHERE sync_status NOT IN ('IGNORED', 'DISCONNECTED')
                ) ranked
                WHERE rn > 1
            )
        """)
    else:
        # SQLite fallback using a correlated subquery to avoid the
        # "UPDATE FROM same table" limitation.
        op.execute("""
            UPDATE repositories
            SET sync_status = 'DISCONNECTED'
            WHERE sync_status NOT IN ('IGNORED', 'DISCONNECTED')
            AND id NOT IN (
                SELECT MIN(id)
                FROM repositories
                WHERE sync_status NOT IN ('IGNORED', 'DISCONNECTED')
                GROUP BY project_id
            )
        """)

    # Add a partial unique index enforcing one active repo per project_id.
    # Active means the repo is not IGNORED or DISCONNECTED.
    op.create_index(
        "ux_repositories_active_project_id",
        "repositories",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("sync_status NOT IN ('IGNORED', 'DISCONNECTED')"),
        sqlite_where=sa.text("sync_status NOT IN ('IGNORED', 'DISCONNECTED')"),
    )


def downgrade():
    op.drop_index("ux_repositories_active_project_id", table_name="repositories")
