"""Trace domain — raw TraceEvent persistence, callback recording and parsing.

Consolidated from the flat ``core/learning`` trace_* modules so the trace
registry owns a single cohesive submodule. Public symbols are re-exported
here for convenience; prefer importing from the concrete module path
(``app.core.learning.trace.parser`` / ``app.core.learning.trace.recorder``)
where the symbol is defined.
"""

from app.core.learning.trace.parser import TraceParser, TraceSequence
from app.core.learning.trace.recorder import (
    TraceCallbackHandler,
    TraceRecorder,
    get_recorder,
    sync_thread_to_graph,
)
from app.core.learning.trace.repository import TraceRepository, trace_repository

__all__ = [
    "TraceParser",
    "TraceSequence",
    "TraceRecorder",
    "get_recorder",
    "TraceCallbackHandler",
    "sync_thread_to_graph",
    "TraceRepository",
    "trace_repository",
]
