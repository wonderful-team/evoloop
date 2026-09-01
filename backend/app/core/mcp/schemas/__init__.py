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
from .tools import (
    GetMcpPromptInput,
    ListMcpPromptsInput,
    ListMcpResourcesInput,
    ReadMcpResourceInput,
    UseMcpServerSchema,
)

# Models with business methods — re-exported from their original modules
