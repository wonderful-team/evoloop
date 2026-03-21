"""
Ruby Language Semantic Provider
"""
from .sem_provider import LanguageSemanticProvider


class RubySemanticProvider(LanguageSemanticProvider):
    """Provider for Ruby language semantic analysis."""

    def get_language_name(self) -> str:
        return "ruby"

    def get_api_query(self) -> str:
        """
        Ruby API frameworks: Rails, Sinatra, Grape, etc.
        """
        return """
        ; Rails route definitions
        (call
          method: (identifier) @method
          arguments: (argument_list
            (string) @path
            [(pair) (hash)]? @options
          )
        )

        ; Controller actions
        (method
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
            method_text = method.text.decode() if method and hasattr(method, "text") else ""
            path_text = path.text.decode().strip("\"'") if path and hasattr(path, "text") else ""
            handler_text = handler.text.decode() if handler and hasattr(handler, "text") else "action"

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


