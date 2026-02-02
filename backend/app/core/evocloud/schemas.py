from typing import Any, Literal
from pydantic import BaseModel, Field


class EvoCloudConfig(BaseModel):
    """Configuration for EvoCloud connectivity."""

    api_url: str
    ws_url: str
    api_key: str | None = None
    api_secret: str | None = None
    
    # Device Identity
    device_name: str | None = "EvoLoop-Desktop"
    
    # Auth (Optional, can be passed dynamically)
    access_token: str | None = None


class CommandData(BaseModel):
    """Structure of a command received from Cloud."""
    
    command_id: str
    type: str # 'chat_message', 'hitl_response', etc.
    content: dict[str, Any] | None = None
    # Flat structure support
    message: str | None = None
    attachments: list[dict[str, Any]] = []
    thread_id: str | None = None
    project_id: int | None = None


class DeviceStatus(BaseModel):
    """Current status of the device connection."""
    
    is_logged_in: bool
    member_id: int | None = None
    device_connected: bool
    device_id: int | None = None
    device_name: str | None = None
