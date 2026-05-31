"""
Extraction Framework
====================

Generic, extensible framework for extracting structured information from
conversation history during the Finish node's audit phase.

Each extractor registers as an ExtractionPlugin with a name, description,
JSON schema, and an async handler. The Finish node dynamically builds a
prompt section from all registered plugins, then dispatches parsed results
to each plugin's handler — all in a single LLM call.
"""

from app.core.engine.extraction.registry import (
    ExtractionContext,
    ExtractionPlugin,
    ExtractionRegistry,
)

__all__ = [
    "ExtractionPlugin",
    "ExtractionRegistry",
    "ExtractionContext",
]
