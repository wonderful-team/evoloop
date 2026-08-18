"""MCP Resources feature implementation."""

import base64
import logging

from mcp import ClientSession

from app.core.mcp.features.base import McpFeature
from app.core.mcp.schemas import (
    McpFeatureCapabilities,
    McpResourceContent,
)

logger = logging.getLogger(__name__)


class McpResourcesFeature(McpFeature):
    """MCP Resources feature - handles resource listing and reading."""

    feature_name = "resources"

    def __init__(self):
        self._session: ClientSession | None = None
        self._server_name: str = ""
        self._resources: list = []
        self._resource_templates: list = []

    async def initialize(self, session: ClientSession, server_name: str) -> None:
        """Initialize by fetching resources from server."""
        self._session = session
        self._server_name = server_name

        try:
            result = await session.list_resources()
            self._resources = result.resources

            # Also try to get resource templates
            try:
                template_result = await session.list_resource_templates()
                self._resource_templates = template_result.resourceTemplates
            except Exception:
                # Not all servers support templates
                self._resource_templates = []

            logger.info(
                f"Loaded {len(self._resources)} resources and "
                f"{len(self._resource_templates)} templates from {server_name}"
            )
        except Exception as e:
            logger.debug(f"Resources not supported by {server_name}: {e}", exc_info=True)
            self._resources = []
            self._resource_templates = []

    async def get_capabilities(self) -> McpFeatureCapabilities:
        """Get resources capabilities."""
        return McpFeatureCapabilities(
            count=len(self._resources),
            templates_count=len(self._resource_templates),
            resources=[
                {
                    "uri": str(r.uri),
                    "name": r.name,
                    "mimeType": r.mimeType,
                    "description": r.description,
                }
                for r in self._resources
            ],
            templates=[
                {"uriTemplate": t.uriTemplate, "name": t.name}
                for t in self._resource_templates
            ],
        )

    def get_resources(self) -> list:
        """Get list of available resources."""
        return self._resources

    def get_resource_templates(self) -> list:
        """Get list of resource templates."""
        return self._resource_templates

    async def read_resource(self, uri: str) -> McpResourceContent:
        """
        Read content from a resource URI.

        Args:
            uri: Resource URI to read

        Returns:
            Dict with content, mime_type, and other metadata
        """
        if not self._session:
            raise RuntimeError("Not connected to MCP server")

        try:
            result = await self._session.read_resource(uri)

            if not result.contents:
                return McpResourceContent(
                    uri=uri,
                    content="",
                    mime_type=None,
                    is_binary=False,
                )

            content = result.contents[0]

            # Handle text content
            if content.text is not None:
                return McpResourceContent(
                    uri=uri,
                    content=content.text,
                    mime_type=content.mimeType,
                    is_binary=False,
                )

            # Handle binary content
            if content.blob is not None:
                # Try to decode as text first
                try:
                    decoded = base64.b64decode(content.blob).decode("utf-8")
                    return McpResourceContent(
                        uri=uri,
                        content=decoded,
                        mime_type=content.mimeType,
                        is_binary=False,
                    )
                except UnicodeDecodeError:
                    # Keep as base64 if can't decode as text
                    return McpResourceContent(
                        uri=uri,
                        content=content.blob,
                        mime_type=content.mimeType,
                        is_binary=True,
                    )

            return McpResourceContent(
                uri=uri,
                content="",
                mime_type=content.mimeType,
                is_binary=False,
            )

        except Exception as e:
            logger.exception(f"Failed to read resource {uri}: {e}")
            raise

    def reset(self) -> None:
        """Reset state."""
        self._session = None
        self._server_name = ""
        self._resources = []
        self._resource_templates = []

    def format_resources_list(self) -> str:
        """Format resources as markdown for display."""
        lines = ["### Available Resources\n"]

        if self._resources:
            lines.append("**Static Resources:**")
            for r in self._resources:
                lines.append(f"- `{r.uri}` - {r.name or 'Unnamed'}")
                if r.description:
                    lines.append(f"  - {r.description}")
                if r.mimeType:
                    lines.append(f"  - MIME: `{r.mimeType}`")
            lines.append("")

        if self._resource_templates:
            lines.append("**Resource Templates:**")
            for t in self._resource_templates:
                lines.append(f"- `{t.uriTemplate}` - {t.name or 'Unnamed'}")
                if t.description:
                    lines.append(f"  - {t.description}")
            lines.append("")

        if not self._resources and not self._resource_templates:
            lines.append("*No resources available on this server.*")

        return "\n".join(lines)
