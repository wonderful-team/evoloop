from typing import Any

from .sem_provider import LanguageSemanticProvider


class GoSemanticProvider(LanguageSemanticProvider):
    def get_language_name(self) -> str:
        return "go"

    def get_structure_query(self) -> str:
        """Query for Go function and method definitions."""
        return """
            (function_declaration name: (identifier) @name body: (block) @body) @function
            (method_declaration name: (field_identifier) @name body: (block) @body) @function
        """

    def get_imports_query(self) -> str:
        """Query for Go imports."""
        return """
            (import_spec path: (string_literal) @module) @import
        """

    def get_api_query(self) -> str:
        return """
        (call_expression
          function: (selector_expression
            operand: (identifier) @obj
            field: (field_identifier) @method)
          arguments: (argument_list
            (interpreted_string_literal) @path
            [(identifier) (func_literal)] @handler
          )
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list[Any]:
        from .api_extractor import APIEndpoint

        method_node = self._get_node(captured_nodes, "method")
        path_node = self._get_node(captured_nodes, "path")
        handler_node = self._get_node(captured_nodes, "handler")

        if not (method_node and path_node and handler_node):
            return []

        method = method_node.text.decode("utf8").upper()
        # HTTP_METHODS validation is handled in dispatcher or here

        path = path_node.text.decode("utf8").strip('"')

        handler_name = "anonymous"
        if handler_node.type == "identifier":
            handler_name = handler_node.text.decode("utf8")

        return [APIEndpoint(
            method=method,
            path=path,
            handler_name=handler_name,
            file_path=file_path,
            line_number=method_node.start_point[0] + 1
        )]
