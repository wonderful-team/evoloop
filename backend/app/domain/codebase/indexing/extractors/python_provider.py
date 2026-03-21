import re
from typing import Any

from .sem_provider import LanguageSemanticProvider


class PythonSemanticProvider(LanguageSemanticProvider):
    """Python semantic provider.
    
    Note: Structure and imports queries are inherited from base class
    which loads them from queries.py to avoid duplication.
    """
    
    def get_language_name(self) -> str:
        return "python"

    def get_api_query(self) -> str:
        return """
        (decorated_definition
          (decorator
            (call
              (attribute
                object: (_) @obj
                attribute: (identifier) @method)
              arguments: (argument_list (_) @path)
            )
          )
          definition: (function_definition name: (identifier) @handler)
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list[Any]:
        # Logic moved from _extract_python
        from .api_extractor import APIEndpoint

        obj_node = self._get_node(captured_nodes, "obj")
        method_node = self._get_node(captured_nodes, "method")
        path_node = self._get_node(captured_nodes, "path")
        handler_node = self._get_node(captured_nodes, "handler")

        if not (obj_node and method_node and path_node and handler_node):
            return []

        method = method_node.text.decode("utf8").lower()
        # Note: HTTP_METHODS check will be handled by the dispatcher or here

        path = path_node.text.decode("utf8").strip("'\"")
        handler = handler_node.text.decode("utf8")

        return [APIEndpoint(
            method=method.upper(),
            path=path,
            handler_name=handler,
            file_path=file_path,
            line_number=method_node.start_point[0] + 1
        )]

    # DB Extraction (SQLAlchemy)
    TABLENAME_PATTERN = re.compile(r'__tablename__\s*=\s*["\']([^"\']+)["\']')
    COLUMN_PATTERN = re.compile(r"([a-zA-Z0-9_]+)\s*:\s*Mapped\[.*\]\s*=\s*mapped_column")

    def extract_db(self, file_path: str, content: str) -> list[Any]:
        from .db_extractor import DBTable
        tables = []
        lines = content.splitlines()
        current_table = None
        current_columns = []

        for line in lines:
            cls_match = re.search(r"class\s+([a-zA-Z0-9_]+)\(Base\)", line)
            if cls_match:
                if current_table and current_columns:
                    tables.append(DBTable(current_table, file_path, list(current_columns)))
                current_table = None
                current_columns = []
                continue

            name_match = self.TABLENAME_PATTERN.search(line)
            if name_match:
                current_table = name_match.group(1)
                continue

            if current_table:
                col_match = self.COLUMN_PATTERN.search(line)
                if col_match:
                    current_columns.append(col_match.group(1))

        if current_table and current_columns:
            tables.append(DBTable(current_table, file_path, list(current_columns)))

        return tables
