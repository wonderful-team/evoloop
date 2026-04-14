"""MCP Prompts feature implementation."""

import logging
from typing import Any

from mcp import ClientSession

from app.core.mcp.features.base import (
    McpFeature,
    McpFeatureCapabilities,
    McpPromptMessage,
    McpPromptResult,
)

logger = logging.getLogger(__name__)


class McpPromptsFeature(McpFeature):
    """MCP Prompts feature - handles prompt templates."""
    
    feature_name = "prompts"
    
    def __init__(self):
        self._session: ClientSession | None = None
        self._server_name: str = ""
        self._prompts: list = []
    
    async def initialize(self, session: ClientSession, server_name: str) -> None:
        """Initialize by fetching prompts from server."""
        self._session = session
        self._server_name = server_name
        
        try:
            result = await session.list_prompts()
            self._prompts = result.prompts
            logger.info(f"Loaded {len(self._prompts)} prompts from {server_name}")
        except Exception as e:
            logger.debug(f"Prompts not supported by {server_name}: {e}")
            self._prompts = []
    
    async def get_capabilities(self) -> McpFeatureCapabilities:
        """Get prompts capabilities."""
        return McpFeatureCapabilities(
            count=len(self._prompts),
            prompts=[
                {
                    "name": p.name,
                    "description": p.description,
                    "arguments": [
                        {"name": arg.name, "required": arg.required, "description": arg.description}
                        for arg in (p.arguments or [])
                    ],
                }
                for p in self._prompts
            ],
        )
    
    def get_prompts(self) -> list:
        """Get list of available prompts."""
        return self._prompts
    
    async def get_prompt(self, name: str, arguments: dict[str, str] | None = None) -> McpPromptResult:
        """
        Get a rendered prompt with optional arguments.
        
        Args:
            name: Prompt name
            arguments: Optional arguments for the prompt
            
        Returns:
            Dict with prompt messages and metadata
        """
        if not self._session:
            raise RuntimeError("Not connected to MCP server")
        
        try:
            result = await self._session.get_prompt(name, arguments=arguments or {})
            
            messages: list[McpPromptMessage] = []
            for msg in result.messages:
                # Handle text content
                if msg.content.type == "text":
                    messages.append(McpPromptMessage(
                        role=msg.role,
                        content=msg.content.text,
                        content_type="text",
                    ))
                # Handle image content
                elif msg.content.type == "image":
                    messages.append(McpPromptMessage(
                        role=msg.role,
                        content=msg.content.data,
                        content_type="image",
                        mime_type=msg.content.mimeType,
                    ))
                # Handle resource content
                elif msg.content.type == "resource":
                    resource = msg.content.resource
                    content = resource.text if hasattr(resource, 'text') else str(resource)
                    resource_uri = resource.uri if hasattr(resource, 'uri') else None
                    messages.append(McpPromptMessage(
                        role=msg.role,
                        content=content,
                        content_type="resource",
                        resource_uri=resource_uri,
                    ))
            
            return McpPromptResult(
                name=name,
                description=result.description,
                messages=messages,
            )
            
        except Exception as e:
            logger.error(f"Failed to get prompt '{name}': {e}")
            raise
    
    def reset(self) -> None:
        """Reset state."""
        self._session = None
        self._server_name = ""
        self._prompts = []
    
    def format_prompts_list(self) -> str:
        """Format prompts as markdown for display."""
        lines = ["### Available Prompts\n"]
        
        if not self._prompts:
            lines.append("*No prompts available on this server.*")
            return "\n".join(lines)
        
        for p in self._prompts:
            lines.append(f"**{p.name}**")
            if p.description:
                lines.append(f"- Description: {p.description}")
            
            if p.arguments:
                lines.append("- Arguments:")
                for arg in p.arguments:
                    req = "(required)" if arg.required else "(optional)"
                    lines.append(f"  - `{arg.name}` {req}: {arg.description or 'No description'}")
            else:
                lines.append("- Arguments: None")
            lines.append("")
        
        return "\n".join(lines)
    
    def find_prompt(self, name: str) -> Any | None:
        """Find a prompt by name."""
        for p in self._prompts:
            if p.name == name:
                return p
        return None
