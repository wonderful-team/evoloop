from app.core.engine.rewind.rewind import (
    MessageNotFoundError,
    NoHumanMessageError,
    RewindError,
)


class PartialRewindError(RewindError):
    """Error raised during partial rewind failures."""

    def __init__(
        self,
        message: str,
        thread_id: str | None = None,
        partial_results: dict | None = None,
        completed_steps: list[str] | None = None,
        failed_steps: list[str] | None = None,
    ):
        super().__init__(message, thread_id)
        self.partial_results = partial_results or {}
        self.completed_steps = completed_steps or []
        self.failed_steps = failed_steps or []


__all__ = [
    "RewindError",
    "MessageNotFoundError",
    "NoHumanMessageError",
    "PartialRewindError",
]
