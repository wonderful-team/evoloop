"""
Shared Tree-sitter Queries for Code Analysis and Extraction.
"""

TREE_SITTER_QUERIES = {
    "python": {
        "defs": """
            (function_definition name: (identifier) @name body: (block) @body) @function
            (class_definition name: (identifier) @name superclasses: (argument_list)? @superclasses body: (block) @body) @class
        """,
        "imports": """
            (import_statement name: (dotted_name) @module) @import
            (import_from_statement module_name: (dotted_name) @module) @import
        """,
    },
    "go": {
        "defs": """
            (function_declaration name: (identifier) @name body: (block) @body) @function
            (method_declaration name: (field_identifier) @name body: (block) @body) @function
        """,
        "imports": """
            (import_spec path: (string_literal) @module) @import
        """,
    },
    "java": {
        "defs": """
            (class_declaration name: (identifier) @name body: (class_body) @body) @class
            (method_declaration name: (identifier) @name body: (block) @body) @function
        """,
        "imports": """
            (import_declaration name: (scoped_identifier) @module) @import
        """,
    },
    "csharp": {
        "defs": """
            (class_declaration name: (identifier) @name body: (declaration_list) @body) @class
            (method_declaration name: (identifier) @name body: (block) @body) @function
        """,
        "imports": """
            (using_directive name: (identifier) @module) @import
            (using_directive name: (qualified_name) @module) @import
        """,
    },
    "javascript": {
        "defs": """
            (function_declaration name: (identifier) @name) @function
            (class_declaration name: (identifier) @name) @class
            (method_definition name: (property_identifier) @name) @function
        """,
        "imports": """
            (import_statement source: (string) @module) @import
            (call_expression function: (identifier) @func arguments: (arguments (string) @module) (#eq? @func "require")) @import
        """,
    },
    "typescript": {
        "defs": """
            (function_declaration name: (identifier) @name) @function
            (class_declaration name: (type_identifier) @name) @class
            (method_definition name: (property_identifier) @name) @function
            (interface_declaration name: (type_identifier) @name) @class
        """,
        "imports": """
            (import_statement source: (string) @module) @import
        """,
    },
    "cpp": {
        "defs": """
            (function_definition declarator: (function_declarator declarator: (identifier) @name) body: (compound_statement) @body) @function
            (class_specifier name: (type_identifier) @name body: (field_declaration_list) @body) @class
        """,
        "imports": """
            (preproc_include path: (string_literal) @module) @import
            (preproc_include path: (system_lib_string) @module) @import
        """,
    },
    "rust": {
        "defs": """
            (function_item name: (identifier) @name body: (block) @body) @function
            (impl_item type: (type_identifier) @name body: (declaration_list) @body) @class
        """,
        "imports": """
            (use_declaration argument: (scoped_identifier) @module) @import
        """,
    },
    "php": {
        "defs": """
            (function_definition name: (name) @name body: (compound_statement) @body) @function
            (class_declaration name: (name) @name body: (declaration_list) @body) @class
        """,
        "imports": """
            (include_expression (string) @module) @import
            (require_expression (string) @module) @import
        """,
    },
    "ruby": {
        "defs": """
            (method name: (identifier) @name) @function
            (class name: (constant) @name) @class
        """,
        "imports": """
            (call method: (identifier) @method arguments: (argument_list (string) @module) (#match? @method "^(require|require_relative)$")) @import
        """,
    },
    "kotlin": {
        "defs": """
            (function_declaration (simple_identifier) @name) @function
            (class_declaration (simple_identifier) @name) @class
            (object_declaration (simple_identifier) @name) @class
        """,
        "imports": """
            (import_header (identifier) @module) @import
        """,
    },
    "swift": {
        "defs": """
            (function_declaration name: (simple_identifier) @name) @function
            (class_declaration name: (simple_identifier) @name) @class
            (struct_declaration name: (simple_identifier) @name) @class
            (enum_declaration name: (simple_identifier) @name) @class
        """,
        "imports": """
            (import_declaration (identifier) @module) @import
        """,
    },
    "sql": {
        "defs": """
            (create_table_statement name: (object_reference (identifier) @name)) @function
            (create_view_statement name: (object_reference (identifier) @name)) @function
            (create_function_statement name: (identifier) @name) @function
        """,
        "imports": "",
    },
    "vue": {
        "defs": """
            (script_element (text) @script)
            (template_element (text) @template)
        """,
        "imports": "",
    },
}
