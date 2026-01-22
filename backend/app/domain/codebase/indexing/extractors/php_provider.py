"""
PHP Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class PHPSemanticProvider(LanguageSemanticProvider):
    """Provider for PHP language semantic analysis."""

    def get_language_name(self) -> str:
        return "php"

    def get_api_query(self) -> str:
        """
        PHP API frameworks: Laravel, Symfony, Slim, etc.
        """
        return """
        ; Laravel/Lumen Route definitions
        (function_call_expression
          function: (member_access_expression
            object: (name) @obj
            name: (name) @method)
          arguments: (arguments
            (string) @path
            [(closure_expression) (name) (array_creation_expression)] @handler
          )
        )

        ; Symfony annotations
        (attribute
          (name) @annotation
          (arguments (string) @path)?
        )

        ; Function with route comment
        (method_declaration
          name: (name) @handler
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        from app.domain.codebase.indexing.base import APIEndpoint

        endpoints = []
        obj = self._get_node(captured_nodes, "obj")
        method = self._get_node(captured_nodes, "method")
        path = self._get_node(captured_nodes, "path")
        handler = self._get_node(captured_nodes, "handler")

        if obj and method and path:
            obj.text.decode() if obj else ""
            method_text = method.text.decode() if method else ""
            path_text = path.text.decode().strip("\"'") if path else ""
            handler_text = handler.text.decode() if handler else "anonymous"

            http_methods = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE", "patch": "PATCH"}
            http_method = http_methods.get(method_text.lower(), "GET")

            endpoints.append(APIEndpoint(
                method=http_method,
                path=path_text,
                handler=handler_text,
                file_path=file_path
            ))

        return endpoints

    def get_structure_query(self) -> str:
        return """
        ; Classes
        (class_declaration
          name: (name) @class.name
        ) @class.def

        ; Methods
        (method_declaration
          name: (name) @function.name
        ) @function.def

        ; Functions
        (function_definition
          name: (name) @function.name
        ) @function.def

        ; Interfaces
        (interface_declaration
          name: (name) @class.name
        ) @class.def

        ; Traits
        (trait_declaration
          name: (name) @class.name
        ) @class.def
        """

    def get_imports_query(self) -> str:
        return """
        ; Use statements
        (namespace_use_declaration
          (namespace_use_clause
            (qualified_name) @import.name
          )
        )

        ; Namespace declarations
        (namespace_definition
          name: (namespace_name) @namespace.name
        )
        """
