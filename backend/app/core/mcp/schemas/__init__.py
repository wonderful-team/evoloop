"""MCP schemas package — unified import entry for all MCP models."""

# Pure DTOs defined in this package
from .auth import (
    AuthConfig,
    AuthToken,
    ElicitationField,
    ElicitationRequest,
    ElicitationValues,
)
from .client import McpPrompt, McpPromptArgument, McpResource, McpServerSummary
from .features import (
    McpFeatureCapabilities,
    McpPromptMessage,
    McpPromptResult,
    McpResourceContent,
)
from .servers import (
    HealthStatus,
    McpServerBase,
    McpServerCreate,
)

__all__ = [
    "AuthConfig",
    "AuthToken",
    "ElicitationField",
    "ElicitationRequest",
    "ElicitationValues",
    "McpPrompt",
    "McpPromptArgument",
    "McpResource",
    "McpServerSummary",
    "McpFeatureCapabilities",
    "McpPromptMessage",
    "McpPromptResult",
    "McpResourceContent",
    "HealthStatus",
    "McpServerBase",
    "McpServerCreate",
]
