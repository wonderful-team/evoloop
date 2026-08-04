"""MCP Tools feature implementation."""

import logging
from typing import Any

from mcp import ClientSession
from pydantic import Field, create_model

from app.core.mcp.features.base import McpFeature, format_mcp_tool_name
from app.core.mcp.schemas import McpFeatureCapabilities
from app.core.tools.base import EvoLoopTool

logger = logging.getLogger(__name__)


class McpToolsFeature(McpFeature):
    """MCP Tools feature - handles tool listing and conversion."""

    feature_name = "tools"

    def __init__(self):
        self._session: ClientSession | None = None
        self._server_name: str = ""
        self._tools: list = []
        self._schemas: dict[str, Any] = {}
        self._native_tools: list[EvoLoopTool] = []

    async def initialize(self, session: ClientSession, server_name: str) -> None:
        """Initialize by fetching tools from server."""
        self._session = session
        self._server_name = server_name

        try:
            result = await session.list_tools()
            self._tools = result.tools
            self._native_tools = self._convert_to_native_tools()
            logger.info(f"Loaded {len(self._native_tools)} tools from {server_name}")
        except Exception as e:
            logger.error(f"Failed to list tools for {server_name}: {e}")
            self._tools = []
            self._native_tools = []

    async def get_capabilities(self) -> McpFeatureCapabilities:
        """Get tools capabilities."""
        return McpFeatureCapabilities(
            count=len(self._tools),
            tools=[
                {"name": t.name, "description": t.description}
                for t in self._tools
            ]
        )

    def get_tools(self) -> list[EvoLoopTool]:
        """Get converted tools."""
        return self._native_tools

    def get_tool_names(self) -> list[str]:
        """Get list of tool names."""
        return [t.name for t in self._native_tools]

    def reset(self) -> None:
        """Reset state."""
        self._session = None
        self._server_name = ""
        self._tools = []
        self._schemas = {}
        self._native_tools = []

    def _convert_to_native_tools(self) -> list[EvoLoopTool]:
        """Convert MCP tools to native EvoLoopTool wrappers."""
        if not self._session:
            return []

        native_tools = []
        session = self._session
        server_name = self._server_name

        for tool in self._tools:

            async def _tool_func(*_args, tool_name: str = tool.name, **kwargs) -> Any:
                return await session.call_tool(tool_name, arguments=kwargs)

            args_schema = self._create_args_schema(tool.name, tool.inputSchema)
            formatted_name = format_mcp_tool_name(server_name, tool.name)

            native_tool = EvoLoopTool(
                func=_tool_func,
                name=formatted_name,
                description=tool.description or f"MCP tool '{tool.name}' from server '{server_name}'",
                args_schema=args_schema,
            )
            native_tools.append(native_tool)

        return native_tools

    def _create_args_schema(self, tool_name: str, schema: dict[str, Any]) -> type:
        """
        Dynamically create a Pydantic model from JSON schema.
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
