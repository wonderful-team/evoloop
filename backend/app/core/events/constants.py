"""Core event system constants."""

#: Default root packages scanned for @event_register handlers at startup.
DEFAULT_SCAN_ROOTS = [
    "app.core",
    "app.domain",
    "app.infrastructure",
]

#: A2A lifecycle event type
A2A_LIFECYCLE = "a2a"

#: Subagent lifecycle event types
SUBAGENT_LIFECYCLE = "subagent"
