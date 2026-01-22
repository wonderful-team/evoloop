from typing import Any

from .sem_provider import LanguageSemanticProvider


class JavaSemanticProvider(LanguageSemanticProvider):
    ANNOTATION_TO_METHOD = {
        "GetMapping": "GET",
        "PostMapping": "POST",
        "PutMapping": "PUT",
        "DeleteMapping": "DELETE",
        "PatchMapping": "PATCH",
    }

    def get_language_name(self) -> str:
        return "java"

    def get_structure_query(self) -> str:
        """Query for Java class and method definitions."""
        return """
            (class_declaration name: (identifier) @name body: (class_body) @body) @class
            (method_declaration name: (identifier) @name body: (block) @body) @function
        """

    def get_imports_query(self) -> str:
        """Query for Java imports."""
        return """
            (import_declaration name: (scoped_identifier) @module) @import
        """

    def get_api_query(self) -> str:
        return """
        (method_declaration
          (modifiers
            (marker_annotation
              name: (identifier) @annotation
            ) @modifier
          )
          name: (identifier) @handler
        )
        (method_declaration
          (modifiers
            (annotation
              name: (identifier) @annotation
              arguments: (annotation_argument_list (string_literal) @path)
            ) @modifier
          )
          name: (identifier) @handler
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list[Any]:
        from .api_extractor import APIEndpoint

        annotation_node = self._get_node(captured_nodes, "annotation")
        path_node = self._get_node(captured_nodes, "path")
        handler_node = self._get_node(captured_nodes, "handler")

        if not (annotation_node and handler_node):
            return []

        annotation = annotation_node.text.decode("utf8")
        method = self.ANNOTATION_TO_METHOD.get(annotation)
        if not method:
            return []

        path = "/"
        if path_node:
            path = path_node.text.decode("utf8").strip('"')

        return [APIEndpoint(
            method=method,
            path=path,
            handler_name=handler_node.text.decode("utf8"),
            file_path=file_path,
            line_number=annotation_node.start_point[0] + 1
        )]
