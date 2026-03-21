from typing import Any

from .sem_provider import LanguageSemanticProvider


class JavaScriptSemanticProvider(LanguageSemanticProvider):
    def get_language_name(self) -> str:
        return "javascript"

    def get_api_query(self) -> str:
        return """
        (call_expression
          function: (member_expression
            object: (identifier) @obj
            property: (property_identifier) @method)
          arguments: (arguments
            [(string) (template_string)] @path
            [(arrow_function) (function_expression) (identifier)] @handler
          )
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list[Any]:
        from .api_extractor import APIEndpoint

        obj_node = self._get_node(captured_nodes, "obj")
        method_node = self._get_node(captured_nodes, "method")
        path_node = self._get_node(captured_nodes, "path")
        handler_node = self._get_node(captured_nodes, "handler")

        if not (obj_node and method_node and path_node and handler_node):
            return []

        method = method_node.text.decode("utf8").lower()
        path_text = path_node.text.decode("utf8")
        if path_text.startswith(("'", '"', "`")):
            path = path_text[1:-1]
        else:
            path = path_text

        handler = "anonymous"
        if handler_node.type == "identifier":
            handler = handler_node.text.decode("utf8")

        return [APIEndpoint(
            method=method.upper(),
            path=path,
            handler_name=handler,
            file_path=file_path,
            line_number=method_node.start_point[0] + 1
        )]


class TypeScriptSemanticProvider(JavaScriptSemanticProvider):
    def get_language_name(self) -> str:
        return "typescript"
