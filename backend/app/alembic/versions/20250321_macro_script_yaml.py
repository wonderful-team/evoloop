"""
Convert macro_script from JSON to YAML storage

Revision ID: 20250321_macro_script_yaml
Revises: 7e8cbf993ca1
Create Date: 2025-03-21 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.utils.yaml import macro_to_yaml

# revision identifiers, used by Alembic.
revision: str = '20250321_macro_script_yaml'
down_revision: Union[str, None] = '7e8cbf993ca1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Convert macro_script from JSONB to Text (YAML format).
    """
    connection = op.get_bind()
    
    # 1. Add temporary column for YAML storage
    op.add_column('learned_skills', sa.Column('macro_script_yaml', sa.Text(), nullable=True))
    
    # 2. Migrate existing data: JSON -> YAML string
    # Note: This is done in Python because we need yaml conversion
    result = connection.execute(sa.text("SELECT id, macro_script FROM learned_skills WHERE macro_script IS NOT NULL"))
    rows = result.fetchall()
    
    for row_id, macro_script_json in rows:
        if macro_script_json:
            try:
                # Convert JSON/dict to YAML string
                yaml_content = macro_to_yaml(macro_script_json)
                connection.execute(
                    sa.text("UPDATE learned_skills SET macro_script_yaml = :yaml WHERE id = :id"),
                    {"yaml": yaml_content, "id": row_id}
                )
            except Exception as e:
                print(f"Warning: Failed to convert macro_script for skill {row_id}: {e}")
                # Keep original JSON as string if conversion fails
                import json
                connection.execute(
                    sa.text("UPDATE learned_skills SET macro_script_yaml = :json_str WHERE id = :id"),
                    {"json_str": json.dumps(macro_script_json), "id": row_id}
                )
    
    # 3. Drop old JSON column
    op.drop_column('learned_skills', 'macro_script')
    
    # 4. Rename new column
    op.alter_column('learned_skills', 'macro_script_yaml', new_column_name='macro_script')


def downgrade() -> None:
    """
    Convert macro_script back from YAML to JSONB.
    """
    connection = op.get_bind()
    
    # 1. Add temporary column for JSON storage
    op.add_column('learned_skills', sa.Column('macro_script_json', sa.JSON(), nullable=True))
    
    # 2. Migrate existing data: YAML string -> JSON
    from app.utils.yaml import macro_from_yaml
    import json
    
    result = connection.execute(sa.text("SELECT id, macro_script FROM learned_skills WHERE macro_script IS NOT NULL"))
    rows = result.fetchall()
    
    for row_id, macro_script_yaml in rows:
        if macro_script_yaml:
            try:
                # Try to parse as YAML first, fallback to JSON
                try:
                    steps = macro_from_yaml(macro_script_yaml)
                except Exception:
                    # Might already be JSON string
                    steps = json.loads(macro_script_yaml)
                
                connection.execute(
                    sa.text("UPDATE learned_skills SET macro_script_json = :json WHERE id = :id"),
                    {"json": json.dumps(steps), "id": row_id}
                )
            except Exception as e:
                print(f"Warning: Failed to convert macro_script for skill {row_id}: {e}")
    
    # 3. Drop old column
    op.drop_column('learned_skills', 'macro_script')
    
    # 4. Rename new column
    op.alter_column('learned_skills', 'macro_script_json', new_column_name='macro_script')
