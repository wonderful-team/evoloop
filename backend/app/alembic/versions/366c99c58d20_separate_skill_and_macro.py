"""分离 skill 与 macro

Revision ID: 366c99c58d20
Revises: a1b2c3d4e5f6
Create Date: 2026-07-17 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "366c99c58d20"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add macro_id to learned_skills
    op.add_column(
        "learned_skills",
        sa.Column("macro_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_learned_skills_macro_id", "learned_skills", ["macro_id"])

    # 2. Add allow_self_healing to macros
    op.add_column(
        "macros",
        sa.Column("allow_self_healing", sa.Boolean(), nullable=False, server_default="1"),
    )

    # 3. Migrate existing deterministic skill macros into the macros table
    conn = op.get_bind()

    # For each LearnedSkill with a macro_script, create a Macro row if one does
    # not already exist for this skill (matched by fallback_skill_id). Reuse the
    # existing Macro row when present and set learned_skills.macro_id.
    skills = conn.execute(
        sa.text(
            """
            SELECT id, name, description, trigger_patterns, parameters,
                   macro_script, status, is_active, namespace, source_thread_id,
                   project_id, member_id, allow_self_healing
            FROM learned_skills
            WHERE macro_script IS NOT NULL AND macro_script != ''
            """
        )
    ).mappings().all()

    for skill in skills:
        existing = conn.execute(
            sa.text("SELECT id FROM macros WHERE fallback_skill_id = :skill_id LIMIT 1"),
            {"skill_id": skill["id"]},
        ).scalar_one_or_none()

        if existing is not None:
            macro_id = existing
        else:
            result = conn.execute(
                sa.text(
                    """
                    INSERT INTO macros (
                        app_map_id, entity, name, description, trigger_patterns,
                        parameters, macro_script, risk_tier, requires_confirmation,
                        status, is_active, namespace, fallback_skill_id,
                        source_thread_id, project_id, member_id, allow_self_healing,
                        created_at, updated_at
                    ) VALUES (
                        NULL, NULL, :name, :description, :trigger_patterns,
                        :parameters, :macro_script, 'ui', FALSE,
                        :status, :is_active, :namespace, :skill_id,
                        :source_thread_id, :project_id, :member_id, :allow_self_healing,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "name": skill["name"],
                    "description": skill["description"] or "",
                    "trigger_patterns": skill["trigger_patterns"],
                    "parameters": skill["parameters"],
                    "macro_script": skill["macro_script"],
                    "status": "verified" if skill["status"] == "verified" else "pending_review",
                    "is_active": bool(skill["is_active"]) and skill["status"] == "verified",
                    "namespace": skill["namespace"],
                    "skill_id": skill["id"],
                    "source_thread_id": skill["source_thread_id"],
                    "project_id": skill["project_id"],
                    "member_id": skill["member_id"],
                    "allow_self_healing": bool(skill["allow_self_healing"]),
                },
            )
            macro_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
            if macro_id is None:
                # SQLite returns None for inserted_primary_key; fetch last row id
                macro_id = conn.execute(sa.text("SELECT last_insert_rowid()")).scalar()

        conn.execute(
            sa.text("UPDATE learned_skills SET macro_id = :macro_id WHERE id = :skill_id"),
            {"macro_id": macro_id, "skill_id": skill["id"]},
        )

    # 4. Drop removed columns from learned_skills
    op.drop_column("learned_skills", "execution_mode")
    op.drop_column("learned_skills", "macro_script")
    op.drop_column("learned_skills", "allow_self_healing")


def downgrade():
    # Restore columns on learned_skills
    op.add_column(
        "learned_skills",
        sa.Column("execution_mode", sa.String(length=20), nullable=False, server_default="agentic"),
    )
    op.add_column(
        "learned_skills",
        sa.Column("macro_script", sa.Text(), nullable=True),
    )
    op.add_column(
        "learned_skills",
        sa.Column("allow_self_healing", sa.Boolean(), nullable=False, server_default="1"),
    )

    # Copy macro script back from linked macros
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE learned_skills
            SET macro_script = macros.macro_script,
                execution_mode = 'deterministic',
                allow_self_healing = macros.allow_self_healing
            FROM macros
            WHERE learned_skills.macro_id = macros.id
            """
        )
    )

    # Drop macro_id and macros.allow_self_healing
    op.drop_index("ix_learned_skills_macro_id", table_name="learned_skills")
    op.drop_column("learned_skills", "macro_id")
    op.drop_column("macros", "allow_self_healing")
