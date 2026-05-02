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
            method_text = method.text.decode() if method else ""
            path_text = path.text.decode().strip("\"'") if path else ""
            handler_text = handler.text.decode() if handler else "anonymous"

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
