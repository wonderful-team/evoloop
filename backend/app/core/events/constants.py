"""Core event system constants."""

#: Default root packages scanned for @event_register handlers at startup.
DEFAULT_SCAN_ROOTS = [
    "app.core",
    "app.domain",
    "app.infrastructure",
]
