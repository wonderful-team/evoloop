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
        from .api_extractor import APIEndpoint

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
                path_text = path.text.decode().strip("\"") if path and hasattr(path, "text") else "/"
                handler_text = handler.text.decode() if handler and hasattr(handler, "text") else "handler"

                endpoints.append(APIEndpoint(
                    method=rest_annotations[ann_text],
                    path=path_text,
                    handler_name=handler_text,
                    file_path=file_path
                ))

        return endpoints
