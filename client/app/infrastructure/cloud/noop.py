"""
No-op Cloud client for when EvoLoop Cloud is not configured.

All operations fail gracefully with SERVICE_DISABLED error.
"""

from app.infrastructure.cloud.protocol import ErrorCode


class NoOpCloudClient:
    """
    No-op implementation of CloudClient.

    Used when EVOLOOP_CLOUD_URL is not configured.
    All methods raise CloudClientError with SERVICE_DISABLED.
    """

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    def _raise_disabled(self, method: str):
        from .client import CloudClientError
        raise CloudClientError(
            ErrorCode.CLOUD_NOT_CONFIGURED,
            f"Cloud service not configured. Set EVOLOOP_CLOUD_URL to use {method}."
        )

    # Device API
    async def register_device(self, *args, **kwargs):
        self._raise_disabled("register_device")

    async def refresh_token(self, *args, **kwargs):
        self._raise_disabled("refresh_token")

    # Agent API
    async def agent_plan(self, *args, **kwargs):
        self._raise_disabled("agent_plan")

    async def agent_decide(self, *args, **kwargs):
        self._raise_disabled("agent_decide")

    # Memory API
    async def memory_recall(self, *args, **kwargs):
        self._raise_disabled("memory_recall")

    async def atlas_query(self, *args, **kwargs):
        self._raise_disabled("atlas_query")

    # Skill API
    async def skill_synthesize(self, *args, **kwargs):
        self._raise_disabled("skill_synthesize")

    async def skill_synthesis_status(self, *args, **kwargs):
        self._raise_disabled("skill_synthesis_status")

    async def skill_download(self, *args, **kwargs):
        self._raise_disabled("skill_download")

    async def skill_list(self, *args, **kwargs):
        return []

    # WebSocket
    async def connect_websocket(self, *args, **kwargs):
        pass

    def on_message(self, *args, **kwargs):
        pass

    async def send_ws_message(self, *args, **kwargs):
        return None


def get_noop_client():
    """Get NoOp cloud client instance."""
    return NoOpCloudClient()
