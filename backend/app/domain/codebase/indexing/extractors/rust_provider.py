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
        ; Functions
        (function_item
          name: (identifier) @function.name
        ) @function.def

        ; Struct definitions
        (struct_item
          name: (type_identifier) @class.name
        ) @class.def

        ; Enum definitions
        (enum_item
          name: (type_identifier) @class.name
        ) @class.def

        ; Trait definitions
        (trait_item
          name: (type_identifier) @class.name
        ) @class.def

        ; Impl blocks
        (impl_item
          type: (type_identifier) @class.name
        ) @class.impl

        ; Macro definitions
        (macro_definition
          name: (identifier) @macro.name
        ) @macro.def
        """

    def get_imports_query(self) -> str:
        return """
        ; Use statements
        (use_declaration
          argument: (use_tree) @import.tree
        )

        ; Extern crate
        (extern_crate_declaration
          name: (identifier) @import.name
        )

        ; Mod declarations
        (mod_item
          name: (identifier) @module.name
        )
        """
