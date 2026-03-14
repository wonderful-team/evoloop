"""
Swift Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class SwiftSemanticProvider(LanguageSemanticProvider):
    """Provider for Swift language semantic analysis."""

    def get_language_name(self) -> str:
        return "swift"

    def get_api_query(self) -> str:
        """
        Swift API frameworks: Vapor, Perfect, Kitura
        """
        return """
        ; Route definitions
        (call_expression
          (navigation_expression
            (simple_identifier) @obj
            (simple_identifier) @method)
          (call_suffix
            (value_arguments
              (value_argument
                (line_string_literal) @path
              )
            )
          )
        )

        ; Function definitions (handlers)
        (function_declaration
          name: (simple_identifier) @handler
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        from .api_extractor import APIEndpoint

        endpoints = []
        self._get_node(captured_nodes, "obj")
        method = self._get_node(captured_nodes, "method")
        path = self._get_node(captured_nodes, "path")
        handler = self._get_node(captured_nodes, "handler")

        if method and path:
            method_text = method.text.decode() if method and hasattr(method, "text") else ""
            path_text = path.text.decode().strip("\"") if path and hasattr(path, "text") else ""
            handler_text = handler.text.decode() if handler and hasattr(handler, "text") else "handler"

            http_methods = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE", "patch": "PATCH"}
            http_method = http_methods.get(method_text.lower(), "GET")

            if method_text.lower() in http_methods:
                endpoints.append(APIEndpoint(
                    method=http_method,
                    path=path_text,
                    handler_name=handler_text,
                    file_path=file_path
                ))

        return endpoints

    def get_structure_query(self) -> str:
        return """
        ; Classes
        (class_declaration
          name: (simple_identifier) @class.name
        ) @class.def

        ; Structs
        (struct_declaration
          name: (simple_identifier) @class.name
        ) @class.def

        ; Enums
        (enum_declaration
          name: (simple_identifier) @class.name
        ) @class.def

        ; Protocols
        (protocol_declaration
          name: (simple_identifier) @class.name
        ) @class.def

        ; Functions
        (function_declaration
          name: (simple_identifier) @function.name
        ) @function.def

        ; Extensions
        (extension_declaration
          (type_identifier) @class.name
        ) @class.extension
        """

    def get_imports_query(self) -> str:
        return """
        ; Import statements
        (import_declaration
          (identifier) @import.name
        )
        """
