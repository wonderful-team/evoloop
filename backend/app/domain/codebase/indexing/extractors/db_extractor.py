
import logging
import re
from dataclasses import dataclass

from app.utils.file import read_file_content

logger = logging.getLogger(__name__)

@dataclass
class DBTable:
    name: str
    file_path: str
    columns: list[str]

class DBExtractor:
    """
    Extracts Database Schema from code.
    Supports SQLAlchemy models.
    """

    # Class inheriting from Base or something with __tablename__
    # This is hard with Regex. But let's try finding __tablename__ = "..."
    TABLENAME_PATTERN = re.compile(r'__tablename__\s*=\s*["\']([^"\']+)["\']')
    COLUMN_PATTERN = re.compile(r'([a-zA-Z0-9_]+)\s*:\s*Mapped\[.*\]\s*=\s*mapped_column') # SQLAlchemy 2.0 style

    async def extract(self, file_path: str) -> list[DBTable]:
        tables = []
        if not file_path.endswith(".py"):
            return []

        try:
            content, _ = read_file_content(file_path)
            if not content: return []

            # Simple State Machine or context aware scan
            lines = content.splitlines()
            current_table = None
            current_columns = []

            for line in lines:
                # Check for table definition
                cls_match = re.search(r'class\s+([a-zA-Z0-9_]+)\(Base\)', line) # Strict Base check
                if cls_match:
                    # New class started, save previous if valid
                    if current_table and current_columns:
                        tables.append(DBTable(current_table, file_path, list(current_columns)))
                    current_table = None # Reset until we find tablename
                    current_columns = []
                    continue

                name_match = self.TABLENAME_PATTERN.search(line)
                if name_match:
                    current_table = name_match.group(1)
                    continue

                if current_table:
                    # Look for columns
                    col_match = self.COLUMN_PATTERN.search(line)
                    if col_match:
                        current_columns.append(col_match.group(1))

            # End of file
            if current_table and current_columns:
                tables.append(DBTable(current_table, file_path, list(current_columns)))

            return tables
        except Exception:
            return []

    async def sync_to_graph(self, project_id: int, tables: list[DBTable]):
        if not tables: return
        try:
            from app.infrastructure.database.graph.driver import get_graph_db
            driver = await get_graph_db()
            async with driver.session() as session:
                for t in tables:
                    await session.run("""
                        MERGE (t:DBTable {name: $name, project_id: $pid})
                        SET t.file = $file
                        
                        WITH t
                        UNWIND $columns as col_name
                        MERGE (c:DBColumn {name: col_name, table: $name, project_id: $pid})
                        MERGE (t)-[:HAS_COLUMN]->(c)
                    """, name=t.name, pid=project_id, file=t.file_path, columns=t.columns)
        except Exception as e:
            logger.error(f"Graph Sync for DB failed: {e}")

db_extractor = DBExtractor()
