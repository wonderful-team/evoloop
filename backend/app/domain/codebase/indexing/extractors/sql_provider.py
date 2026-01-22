"""
SQL Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class SQLSemanticProvider(LanguageSemanticProvider):
    """Provider for SQL semantic analysis (DDL, DML extraction)."""

    def get_language_name(self) -> str:
        return "sql"

    def get_api_query(self) -> str:
        """SQL doesn't have API endpoints. Return empty query."""
        return ""

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        return []

    def get_structure_query(self) -> str:
        """
        Extract SQL DDL structures: tables, views, procedures, functions.
        """
        return """
        ; CREATE TABLE
        (create_table_statement
          name: (object_reference
            (identifier) @table.name
          )
        ) @table.def

        ; CREATE VIEW
        (create_view_statement
          name: (object_reference
            (identifier) @view.name
          )
        ) @view.def

        ; CREATE FUNCTION
        (create_function_statement
          name: (identifier) @function.name
        ) @function.def

        ; CREATE PROCEDURE/PROC
        (create_procedure_statement
          name: (identifier) @function.name
        ) @function.def

        ; CREATE INDEX
        (create_index_statement
          name: (identifier) @index.name
        ) @index.def

        ; ALTER TABLE
        (alter_table_statement
          name: (object_reference
            (identifier) @table.name
          )
        ) @table.alter
        """

    def get_imports_query(self) -> str:
        """SQL doesn't have imports. Return empty query."""
        return ""

    def extract_db(self, file_path: str, content: str) -> list:
        """
        Extract database schema from SQL files.
        """
        import re

        tables = []

        # Match CREATE TABLE statements
        table_pattern = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\("
        for match in re.finditer(table_pattern, content, re.IGNORECASE):
            tables.append({
                "name": match.group(1),
                "type": "table",
                "file": file_path
            })

        # Match CREATE VIEW statements
        view_pattern = r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+[`\"\[]?(\w+)[`\"\]]?"
        for match in re.finditer(view_pattern, content, re.IGNORECASE):
            tables.append({
                "name": match.group(1),
                "type": "view",
                "file": file_path
            })

        return tables
