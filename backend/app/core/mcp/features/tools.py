"""MCP Tools feature implementation."""

import logging
import re
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from pydantic import Field, create_model

from app.core.mcp.features.base import McpFeature

logger = logging.getLogger(__name__)


class McpToolsFeature(McpFeature):
    """MCP Tools feature - handles tool listing and conversion."""
    
    feature_name = "tools"
    
    def __init__(self):
        self._session: ClientSession | None = None
        self._server_name: str = ""
        self._tools: list = []
        self._schemas: dict[str, Any] = {}
        self._lc_tools: list[StructuredTool] = []
    
    async def initialize(self, session: ClientSession, server_name: str) -> None:
        """Initialize by fetching tools from server."""
        self._session = session
        self._server_name = server_name
        
        try:
            result = await session.list_tools()
            self._tools = result.tools
            self._lc_tools = self._convert_to_langchain_tools()
            logger.info(f"Loaded {len(self._lc_tools)} tools from {server_name}")
        except Exception as e:
            logger.error(f"Failed to list tools for {server_name}: {e}")
            self._tools = []
            self._lc_tools = []
    
    async def get_capabilities(self) -> dict[str, Any]:
        """Get tools capabilities."""
        return {
            "count": len(self._tools),
            "tools": [
                {"name": t.name, "description": t.description}
                for t in self._tools
            ]
        }
    
    def get_tools(self) -> list[StructuredTool]:
        """Get converted LangChain tools."""
        return self._lc_tools
    
    def get_tool_names(self) -> list[str]:
        """Get list of tool names."""
        return [t.name for t in self._lc_tools]
    
    def reset(self) -> None:
        """Reset state."""
        self._session = None
        self._server_name = ""
        self._tools = []
        self._schemas = {}
        self._lc_tools = []
    
    def _convert_to_langchain_tools(self) -> list[StructuredTool]:
        """Convert MCP tools to LangChain StructuredTools."""
        if not self._session:
            return []
        
        lc_tools = []
        session = self._session  # Capture for closure
        server_name = self._server_name
        
        for tool in self._tools:
            # Create async function that calls the MCP tool
            async def _tool_func(*_args, tool_name: str = tool.name, **kwargs) -> Any:
                return await session.call_tool(tool_name, arguments=kwargs)
            
            # Create Pydantic schema from JSON schema
            args_schema = self._create_args_schema(tool.name, tool.inputSchema)
            
            # Generate standardized tool name
            formatted_name = self._format_tool_name(server_name, tool.name)
            
            lc_tool = StructuredTool.from_function(
                func=None,
                coroutine=_tool_func,
                name=formatted_name,
                description=tool.description or f"MCP tool '{tool.name}' from server '{server_name}'",
                args_schema=args_schema,
            )
            lc_tools.append(lc_tool)
        
        return lc_tools
    
    def _format_tool_name(self, server_name: str, tool_name: str) -> str:
        """
        Format tool name to standardized format.
        
        Format: mcp__{server}__{tool}
        OpenAI restriction: ^[a-zA-Z0-9_-]{1,64}$
        
        Args:
            server_name: MCP server name
            tool_name: Original tool name
            
        Returns:
            Formatted tool name (max 64 chars)
        """
        # Sanitize names
        safe_server = re.sub(r'[^a-zA-Z0-9_]', '_', server_name).lower()
        safe_tool = re.sub(r'[^a-zA-Z0-9_]', '_', tool_name).lower()
        
        formatted = f"mcp__{safe_server}__{safe_tool}"
        
        # Truncate to 64 chars (OpenAI limit)
        if len(formatted) > 64:
            formatted = formatted[:64]
        
        return formatted
    
    def _create_args_schema(self, tool_name: str, schema: dict[str, Any]) -> type:
        """
        Dynamically create a Pydantic model from JSON schema.
        
        Args:
            tool_name: Name of the tool (for model naming)
            schema: JSON schema dict
            
        Returns:
            Pydantic model class
        """
        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        
        fields = {}
        required_fields = set(schema.get("required", []))
        properties = schema.get("properties", {})
        
        for field_name, field_def in properties.items():
            field_type = type_map.get(field_def.get("type", "string"), str)
            description = field_def.get("description", "")
            
            if field_name in required_fields:
                fields[field_name] = (field_type, Field(description=description))
            else:
                fields[field_name] = (
                    field_type | None,
                    Field(default=None, description=description),
                )
        
        model_name = f"{tool_name}Input"
        return create_model(model_name, **fields)
