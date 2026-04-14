"""
Rewind Exceptions
=================

Custom exceptions for the rewind system.
"""


class RewindError(Exception):
    """Base exception for rewind operations."""

    def __init__(self, message: str, thread_id: str | None = None):
        super().__init__(message)
        self.thread_id = thread_id
        self.message = message


class PartialRewindError(RewindError):
    """
    Raised when a rewind operation partially succeeds.
    
    Some handlers may have completed successfully while others failed.
    """

    def __init__(
        self,
        message: str,
        thread_id: str | None = None,
        completed_steps: list[str] = None,
        failed_steps: list[str] = None,
        partial_results: dict = None
    ):
        super().__init__(message, thread_id)
        self.completed_steps = completed_steps or []
        self.failed_steps = failed_steps or []
        self.partial_results = partial_results or {}


class MessageNotFoundError(RewindError):
    """Raised when the target message for rewind is not found."""
    pass


class NoHumanMessageError(RewindError):
    """Raised when no human message exists to rewind to."""
    pass


class CheckpointNotFoundError(RewindError):
    """Raised when no matching checkpoint is found for rewind."""
    pass
