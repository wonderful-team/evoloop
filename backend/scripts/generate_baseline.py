#!/usr/bin/env python3
"""
Generate a baseline alembic migration from SQLAlchemy models metadata.
No database connection required. Run on the server after git pull.

Usage:
    cd /www/wwwroot/evoloop.limestone.info/backend
    uv run python scripts/generate_baseline.py
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Setup Python path so we can import app.models
# ---------------------------------------------------------------------------
backend_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

# ---------------------------------------------------------------------------
# 2. Import models metadata
# ---------------------------------------------------------------------------
from app.infrastructure.database.sql.database import Base
from app.models import SQLModel
from sqlalchemy import MetaData, schema as sa_schema
from sqlalchemy.dialects import postgresql


def generate_baseline():
    # Merge metadata from both declarative bases
    combined = MetaData()

    for table in Base.metadata.sorted_tables:
        if table.name not in combined.tables:
            table.tometadata(combined)

    for table in SQLModel.metadata.sorted_tables:
        if table.name not in combined.tables:
            table.tometadata(combined)

    dialect = postgresql.dialect()
    statements: list[tuple[str, str]] = []

    # Ensure pgvector extension exists (idempotent)
    statements.append(("extension", "CREATE EXTENSION IF NOT EXISTS vector"))

    # -----------------------------------------------------------------------
    # 3. Generate CREATE TABLE / INDEX / FK statements
    # -----------------------------------------------------------------------
    for table in combined.sorted_tables:
        # CREATE TABLE (includes PK, Unique, Check constraints)
        create_sql = str(sa_schema.CreateTable(table).compile(dialect=dialect))
        statements.append(("table", create_sql.strip()))

        # CREATE INDEX (explicit indexes only; PK/Unique indexes are inside CREATE TABLE)
        for idx in table.indexes:
            create_idx = str(sa_schema.CreateIndex(idx).compile(dialect=dialect))
            statements.append(("index", create_idx.strip()))

        # FOREIGN KEY constraints (PostgreSQL CreateTable excludes these by default)
        for fk in table.foreign_key_constraints:
            add_fk = str(sa_schema.AddConstraint(fk).compile(dialect=dialect))
            statements.append(("fk", add_fk.strip()))

    # -----------------------------------------------------------------------
    # 4. Build the migration Python file
    # -----------------------------------------------------------------------
    revision_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")

    lines = [
        '"""baseline',
        "",
        f"Revision ID: {revision_id}",
        "Revises: ",
        f"Create Date: {now}",
        "",
        '"""',
        "from alembic import op",
        "import sqlalchemy as sa",
        "from sqlalchemy.dialects import postgresql",
        "",
        f'revision = "{revision_id}"',
        "down_revision = None",
        "branch_labels = None",
        "depends_on = None",
        "",
        "def upgrade() -> None:",
    ]

    for _, sql in statements:
        # Escape triple-quotes inside the SQL string
        safe_sql = sql.replace('"""', '\\"\\"\\"')
        lines.append(f'    op.execute(sa.text("""{safe_sql}"""))')

    lines.append("")
    lines.append("def downgrade() -> None:")
    # Drop tables in reverse topological order (CASCADE handles FKs / indexes)
    for table in reversed(list(combined.sorted_tables)):
        lines.append(f'    op.execute(sa.text("DROP TABLE IF EXISTS {table.name} CASCADE"))')

    content = "\n".join(lines) + "\n"

    # -----------------------------------------------------------------------
    # 5. Write file
    # -----------------------------------------------------------------------
    versions_dir = backend_dir / "app" / "alembic" / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    filename = versions_dir / f"{revision_id}_baseline.py"
    filename.write_text(content, encoding="utf-8")

    print(f"✓ Generated baseline migration")
    print(f"  File:    {filename}")
    print(f"  Rev ID:  {revision_id}")
    print(f"  Tables:  {len(combined.tables)}")


if __name__ == "__main__":
    generate_baseline()
