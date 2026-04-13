"""URL Elicitation support for MCP servers."""

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.utils.model_helpers import LegacyDictMixin

logger = logging.getLogger(__name__)


class ElicitationValues(BaseModel, LegacyDictMixin):
    """Values provided for an elicitation request."""
    model_config = ConfigDict(extra="allow")


class ElicitationField(BaseModel, LegacyDictMixin):
    """A field requiring user input."""
    name: str
    description: str
    required: bool = True
    sensitive: bool = False
    field_type: str = "string"  # string, number, boolean, url


class ElicitationRequest(BaseModel, LegacyDictMixin):
    """Request for additional configuration."""
    server_name: str
    message: str
    fields: list[ElicitationField] = Field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Backward compatibility for existing code calling to_dict manually."""
        return {
            "server_name": self.server_name,
            "message": self.message,
            "fields": [
                {
                    "name": f.name,
                    "description": f.description,
                    "required": f.required,
                    "sensitive": f.sensitive,
                    "type": f.field_type,
                }
                for f in self.fields
            ]
        }


class McpElicitationHandler:
    """
    Handles MCP URL Elicitation errors (-32042).
    
    When an MCP server returns an elicitation error, it needs
    additional configuration from the user before it can proceed.
    """
    
    def __init__(self):
        self._pending: dict[str, ElicitationRequest] = {}
        self._futures: dict[str, asyncio.Future] = {}
    
    def parse_elicitation_error(self, server_name: str, error_data: dict) -> ElicitationRequest:
        """
        Parse elicitation error from MCP server.
        
        Args:
            server_name: Server that returned the error
            error_data: Error data from MCP response
            
        Returns:
            ElicitationRequest
        """
        elicitation = error_data.get("elicitation", {})
        message = elicitation.get("message", "Additional configuration required")
        required_fields = elicitation.get("required", [])
        fields_def = elicitation.get("fields", {})
        
        fields = []
        for field_name in required_fields:
            field_def = fields_def.get(field_name, {})
            fields.append(ElicitationField(
                name=field_name,
                description=field_def.get("description", f"Please provide {field_name}"),
                required=True,
                sensitive=field_def.get("sensitive", False),
                field_type=field_def.get("type", "string"),
            ))
        
        request = ElicitationRequest(
            server_name=server_name,
            message=message,
            fields=fields
        )
        
        self._pending[server_name] = request
        
        return request
    
    async def wait_for_input(self, server_name: str, timeout: float = 300.0) -> ElicitationValues:
        """
        Wait for user to provide elicitation values.
        
        Args:
            server_name: Server waiting for input
            timeout: Timeout in seconds
            
        Returns:
            Dict of field values
        """
        if server_name not in self._pending:
            raise ValueError(f"No pending elicitation for {server_name}")
        
        # Create future
        future = asyncio.get_event_loop().create_future()
        self._futures[server_name] = future
        
        try:
            values = await asyncio.wait_for(future, timeout=timeout)
            return values
        except asyncio.TimeoutError:
            raise RuntimeError(f"Elicitation timeout for {server_name}")
        finally:
            self._futures.pop(server_name, None)
            self._pending.pop(server_name, None)
    
    def provide_input(self, server_name: str, values: ElicitationValues) -> None:
        """
        Provide values for pending elicitation.
        
        Args:
            server_name: Server name
            values: Field values
        """
        if server_name not in self._futures:
            raise ValueError(f"No pending elicitation for {server_name}")
        
        future = self._futures[server_name]
        future.set_result(values)
    
    def get_pending(self, server_name: str) -> ElicitationRequest | None:
        """Get pending elicitation request for a server."""
        return self._pending.get(server_name)
    
    def has_pending(self, server_name: str) -> bool:
        """Check if there's a pending elicitation for a server."""
        return server_name in self._pending
    
    def cancel(self, server_name: str) -> None:
        """Cancel pending elicitation."""
        if server_name in self._futures:
            future = self._futures[server_name]
            if not future.done():
                future.cancel()
        self._futures.pop(server_name, None)
        self._pending.pop(server_name, None)


# Global instance
mcp_elicitation_handler = McpElicitationHandler()
