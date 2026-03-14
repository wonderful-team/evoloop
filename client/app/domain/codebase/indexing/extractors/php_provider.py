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
        ; Laravel/Lumen Route definitions (Static: Route::get)
        (scoped_call_expression
          (name) @obj
          (name) @method
          (arguments
            (argument (string) @path)
            (argument [(anonymous_function) (array_creation_expression) (string)] @handler)
          )
        )
        
        ; Laravel/Lumen Instance definitions ($router->get)
        (member_call_expression
          (variable_name) @obj
          (name) @method
          (arguments
            (argument (string) @path)
            (argument [(anonymous_function) (array_creation_expression) (string)] @handler)
          )
        )

        ; Symfony annotations (PHP 8 Attributes)
        (attribute
            (name) @annotation
            (arguments (argument (string) @path))?
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        from .api_extractor import APIEndpoint

        endpoints = []
        obj = self._get_node(captured_nodes, "obj")
        method = self._get_node(captured_nodes, "method")
        path = self._get_node(captured_nodes, "path")
        handler = self._get_node(captured_nodes, "handler")

        if obj and method and path:
            method_text = method.text.decode() if method and hasattr(method, "text") else ""
            path_text = path.text.decode().strip("\"'") if path and hasattr(path, "text") else ""
            handler_text = handler.text.decode() if handler and hasattr(handler, "text") else "anonymous"

            http_methods = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE", "patch": "PATCH"}
            http_method = http_methods.get(method_text.lower(), "GET")

            line_number = method.start_point[0] + 1 if method else 0

            endpoints.append(APIEndpoint(
                method=http_method,
                path=path_text,
                handler_name=handler_text,
                file_path=file_path,
                line_number=line_number
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
