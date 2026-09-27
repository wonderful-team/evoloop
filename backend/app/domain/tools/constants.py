"""Constants for the tools domain."""

# -----------------------------------------------------------------------------
# Database tool guards
# -----------------------------------------------------------------------------

DANGEROUS_KEYWORDS = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|REPLACE|MERGE|EXEC|EXECUTE)\b"
"""Regex matching SQL keywords blocked by the read-only query tool."""

MAX_ROWS = 1000
"""Hard row limit returned by the SQL query tool."""
