"""
Rust Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class RustSemanticProvider(LanguageSemanticProvider):
    """Provider for Rust language semantic analysis."""

    def get_language_name(self) -> str:
        return "rust"

    def get_api_query(self) -> str:
        """
        Rust web frameworks: Actix-web, Rocket, Axum, Warp
        """
        return """
        ; Actix-web route attributes
        (attribute_item
          (attribute
            (identifier) @method
            arguments: (token_tree
              (string_literal) @path
            )
          )
        )

        ; Rocket route macros
        (attribute_item
          (attribute
            (identifier) @rocket_route
            arguments: (token_tree
              (string_literal) @path
            )
          )
          (#match? @rocket_route "^(get|post|put|delete|patch)$")
        )

        ; Function definition (handler)
        (function_item
          name: (identifier) @handler
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list:
        from .api_extractor import APIEndpoint

        endpoints = []
        method = self._get_node(captured_nodes, "method")
        path = self._get_node(captured_nodes, "path")
        handler = self._get_node(captured_nodes, "handler")

        if method and path:
            method_text = method.text.decode() if method else ""
            path_text = path.text.decode().strip("\"") if path else ""
            handler_text = handler.text.decode() if handler else "handler"

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
