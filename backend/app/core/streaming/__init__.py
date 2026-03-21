"""
Streaming module - Phase 3 Refactored
=====================================

The EnhancedStreamManager class has been eliminated.
Its functionality is now integrated directly into TransparentCallbackHandler.

For structured stream events, use TransparentCallbackHandler:
    handler = TransparentCallbackHandler(thread_id)
    await handler.emit_tool_progress(tool_name, message, progress)
    await handler.emit_thinking(message, detail)
    await handler.emit_checkpoint(checkpoint_id, name, file_count)

For checkpoint tools with streaming decorators:
    from app.core.checkpoint.batch_tracker import checkpoint_with_stream
"""

# Phase 3: Stream functionality integrated into TransparentCallbackHandler
# No separate exports needed - all streaming is now unified

__all__ = []
