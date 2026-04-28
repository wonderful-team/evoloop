"""API schemas for devices routes."""

from typing import Any

from app.api.schemas.responses import BaseAPIResponse
from app.infrastructure.pydantic_base import DynamicBaseModel


class BindResponse(BaseAPIResponse):
    """Device bind response."""
    status: str
    data: dict[str, Any] | None = None

class DebugStatusResponse(BaseAPIResponse):
    """EvoCloud debug status response."""
    is_logged_in: bool
    token_prefix: str | None
    device_id: str | None
    device_name: str
    is_connected: bool
    api_url: str

class BindClientRequest(DynamicBaseModel):
    client_id: str

class CommandParams(DynamicBaseModel):
    """Dynamic command parameters for device control.
    
    Different command_types accept different parameters.
    Extra fields are allowed to support all command types.
    """

class SendCommandRequest(DynamicBaseModel):
    command_type: str
    params: CommandParams = CommandParams()
