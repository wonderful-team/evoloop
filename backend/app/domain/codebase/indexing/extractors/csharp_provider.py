from typing import Any

from .sem_provider import LanguageSemanticProvider


class CSharpSemanticProvider(LanguageSemanticProvider):
    ANNOTATION_TO_METHOD = {
        "HttpGet": "GET",
        "HttpPost": "POST",
        "HttpPut": "PUT",
        "HttpDelete": "DELETE",
        "HttpPatch": "PATCH",
    }

    def get_language_name(self) -> str:
        return "csharp"

    def get_api_query(self) -> str:
        return """
        (method_declaration
          (attribute_list
            (attribute
              name: (identifier) @method_attr
              (attribute_argument_list
                (attribute_argument) @path_arg
              )?
            )
          )
          name: (identifier) @handler
        )
        """

    def parse_api_match(self, captured_nodes: dict, file_path: str) -> list[Any]:
        from .api_extractor import APIEndpoint

        attr_node = self._get_node(captured_nodes, "method_attr")
        path_arg_node = self._get_node(captured_nodes, "path_arg")
        handler_node = self._get_node(captured_nodes, "handler")

        if not (attr_node and handler_node):
            return []

        attr_name = attr_node.text.decode("utf8")
        method = self.ANNOTATION_TO_METHOD.get(attr_name)
        if not method:
            return []

        path = "/"
        if path_arg_node:
            path_text = path_arg_node.text.decode("utf8").strip()
            if path_text.startswith('"') and path_text.endswith('"'):
                path = path_text.strip('"')

        return [APIEndpoint(
            method=method,
            path=path,
            handler_name=handler_node.text.decode("utf8"),
            file_path=file_path,
            line_number=attr_node.start_point[0] + 1
        )]
