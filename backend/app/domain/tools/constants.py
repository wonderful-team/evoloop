"""Constants for the tools domain."""

import os

# -----------------------------------------------------------------------------
# Dynamic tool creation
# -----------------------------------------------------------------------------

DYNAMIC_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "../../../tools/dynamic")
"""Directory where dynamically created Python tools are persisted."""

DYNAMIC_TOOL_ALLOWED_IMPORTS = {
    "json",
    "math",
    "datetime",
    "re",
    "random",
    "typing",
    "collections",
    "itertools",
    "functools",
}
"""Modules allowed in dynamic tool source code."""

DYNAMIC_TOOL_UNSAFE_FUNCTIONS = {"eval", "exec", "compile", "open", "input"}
"""Built-in functions forbidden in dynamic tool source code."""

# -----------------------------------------------------------------------------
# Database tool guards
# -----------------------------------------------------------------------------

DANGEROUS_KEYWORDS = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|REPLACE|MERGE|EXEC|EXECUTE)\b"
"""Regex matching SQL keywords blocked by the read-only query tool."""

MAX_ROWS = 1000
"""Hard row limit returned by the SQL query tool."""

# -----------------------------------------------------------------------------
# Document reader limits
# -----------------------------------------------------------------------------

MAX_PAGES = 20
"""Maximum number of PDF pages read in one call."""

MAX_ROWS_PER_SHEET = 100
"""Maximum number of Excel rows read per sheet in one call."""

DOCX_HEADINGS_PREVIEW_LIMIT = 20
"""Maximum number of DOCX headings returned during inspection."""
