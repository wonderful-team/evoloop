"""API schemas for utils routes."""

from app.api.schemas.responses import BaseAPIResponse, ListResponse
from typing import Any, Optional

class EvoloopStatusResponse(BaseAPIResponse):
    connected: bool
    device_key: str | None = None
    device_name: str
