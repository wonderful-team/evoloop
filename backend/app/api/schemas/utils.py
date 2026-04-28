"""API schemas for utils routes."""

from app.api.schemas.responses import BaseAPIResponse


class EvoloopStatusResponse(BaseAPIResponse):
    connected: bool
    device_key: str | None = None
    device_name: str
