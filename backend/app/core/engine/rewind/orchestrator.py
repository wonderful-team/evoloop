from typing import Any

from app.core.engine.rewind.rewind import perform_rewind


class RewindOrchestrator:
    """Backward-compatible shim class wrapping perform_rewind."""

    def __init__(self, event_bus: Any = None):
        self.event_bus = event_bus

    async def perform_rewind(
        self,
        thread_id: str,
        target_message_id: str | None = None,
        include_target: bool = True,
        revert_files: bool = True,
        reset_state: bool = False,
        reason: str = "user_request",
    ) -> Any:
        return await perform_rewind(
            thread_id=thread_id,
            target_message_id=target_message_id,
            include_target=include_target,
            revert_files=revert_files,
            reset_state=reset_state,
            reason=reason,
        )
