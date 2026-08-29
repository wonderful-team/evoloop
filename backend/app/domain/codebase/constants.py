"""Codebase domain-wide constants."""

import os

from app.constants import EXTENSION_MAP, SOFTWARE_DIRECTORIES, SOFTWARE_INDICATORS

# Names of generation artifacts that can be dispatched and tracked.
GENERATION_ITEMS = frozenset({"wiki", "appmap", "summary"})

# Maximum directory depth for the code-file scan heuristic.
CLASSIFIER_MAX_DEPTH = 2

# Minimum number of code files required to classify a project as SOFTWARE.
CODE_FILE_THRESHOLD = 3

# Combined set of files/directories that strongly indicate a software project.
SOFTWARE_MARKERS = SOFTWARE_INDICATORS | SOFTWARE_DIRECTORIES

# File extensions recognized as source code.
CODE_EXTENSIONS = set(EXTENSION_MAP.keys())

# Seconds of inactivity before accumulated changes are dispatched.
BATCH_DEBOUNCE = 180.0

# Max seconds a single index_file task may run before being abandoned.
PER_FILE_TIMEOUT = 120.0

# Maximum number of modified files dispatched in one handler cycle.
MAX_PER_CYCLE = 20

# Number of files dispatched in each chunk within a handler cycle.
BATCH_SIZE = 10

# Seconds to wait between dispatch chunks.
BATCH_INTERVAL = 1.0

# Seconds before re-scheduling leftover files that exceed MAX_PER_CYCLE.
LEFTOVER_RETRY_DEBOUNCE = 5.0

# Semaphore limit for concurrent file extraction during full indexing.
EXTRACT_CONCURRENCY = max(4, (os.cpu_count() or 4) * 2)

# Number of texts to embed and persist together in a single window.
TEXTS_PER_WINDOW = 32

# Max wait time for the batched embedder to fill a batch.
BATCH_MAX_WAIT_MS = 50

# Character cap for a single document text passed to the embedder.
EMBEDDING_TEXT_CAP = 8000

# Maximum length of the whole-file summary document content.
FILE_SUMMARY_MAX_LENGTH = 15000

# Minimum non-empty content length to trigger a safe-indexing warning.
MIN_CONTENT_LENGTH_FOR_SAFE_INDEXING = 50

# Max seconds a single background index task may run before timing out.
INDEX_FILE_TIMEOUT = 120.0

# Shared Tree-sitter queries for code analysis and extraction.
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
            (import_declaration (scoped_identifier) @module) @import
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
    "c": {
        "defs": """
            (function_definition declarator: (function_declarator declarator: (identifier) @name) body: (compound_statement) @body) @function
            (struct_specifier name: (type_identifier) @name body: (field_declaration_list)? @body) @class
        """,
        "imports": """
            (preproc_include path: (string_literal) @module) @import
            (preproc_include path: (system_lib_string) @module) @import
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
"""Shared Tree-sitter queries for code analysis and extraction."""
