"""
Kotlin Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class KotlinSemanticProvider(LanguageSemanticProvider):
    """Provider for Kotlin language semantic analysis."""

    def get_language_name(self) -> str:
        return "kotlin"

    def get_api_query(self) -> str:
        """
        Kotlin API frameworks: Spring Boot, Ktor
        """
        return """
        ; Spring annotations
        (annotation
          (user_type
            (simple_identifier) @annotation
          )
          (value_arguments
            (value_argument
              (string_literal) @path
            )
          )?
        )

        ; Function with annotation
        (function_declaration
          (modifiers
            (annotation) @func_annotation
          )?
          (simple_identifier) @handler
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        from app.domain.codebase.indexing.base import APIEndpoint

        endpoints = []
        annotation = self._get_node(captured_nodes, "annotation")
        path = self._get_node(captured_nodes, "path")
        handler = self._get_node(captured_nodes, "handler")

        rest_annotations = {
            "GetMapping": "GET",
            "PostMapping": "POST",
            "PutMapping": "PUT",
            "DeleteMapping": "DELETE",
            "PatchMapping": "PATCH",
            "RequestMapping": "GET"
        }

        if annotation:
            ann_text = annotation.text.decode() if annotation else ""
            if ann_text in rest_annotations:
                path_text = path.text.decode().strip("\"") if path else "/"
                handler_text = handler.text.decode() if handler else "handler"

                endpoints.append(APIEndpoint(
                    method=rest_annotations[ann_text],
                    path=path_text,
                    handler=handler_text,
                    file_path=file_path
                ))

        return endpoints

    def get_structure_query(self) -> str:
        return """
        ; Classes
        (class_declaration
          (simple_identifier) @class.name
        ) @class.def

        ; Objects (singleton)
        (object_declaration
          (simple_identifier) @class.name
        ) @class.def

        ; Functions
        (function_declaration
          (simple_identifier) @function.name
        ) @function.def

        ; Interfaces
        (interface_declaration
          (simple_identifier) @class.name
        ) @class.def

        ; Data classes
        (class_declaration
          (modifiers
            (class_modifier) @modifier
          )
          (simple_identifier) @class.name
          (#eq? @modifier "data")
        ) @class.def
        """

    def get_imports_query(self) -> str:
        return """
        ; Import statements
        (import_header
          (identifier) @import.name
        )

        ; Package declaration
        (package_header
          (identifier) @package.name
        )
        """
