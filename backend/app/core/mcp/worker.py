"""Worker-specific MCP management for isolated per-worker connections."""

import logging
from contextlib import AsyncExitStack
from typing import Any

from app.core.mcp.auth.manager import mcp_auth_manager
from app.core.mcp.config import McpServerConfig
from app.core.mcp.features.prompts import McpPromptsFeature
from app.core.mcp.features.resources import McpResourcesFeature
from app.core.mcp.features.tools import McpToolsFeature
from app.core.mcp.health import McpHealthChecker
from app.core.mcp.schemas import McpPromptResult, McpResourceContent
from app.core.mcp.transport import McpTransport
from app.core.tools.base import EvoLoopTool

logger = logging.getLogger(__name__)


class WorkerMcpSession:
    """
    An isolated MCP session for a specific Worker instance.
    
    Each Worker gets its own set of MCP connections that are:
    1. Separate from global MCP connections
    2. Lifecycle-bound to the Worker (created on start, cleaned up on end)
    3. Configurable via Skill/Worker definition
    """

    def __init__(self, worker_id: str, worker_name: str):
        self.worker_id = worker_id
        self.worker_name = worker_name

        # Connection state
        self._sessions: dict[str, Any] = {}
        self._stacks: dict[str, AsyncExitStack] = {}
        self._configs: dict[str, McpServerConfig] = {}

        # Features
        self._tools_feature: dict[str, McpToolsFeature] = {}
        self._resources_feature: dict[str, McpResourcesFeature] = {}
        self._prompts_feature: dict[str, McpPromptsFeature] = {}

        # Sub-components
        self._transport = McpTransport()
        self._health_checker = McpHealthChecker()

        logger.debug(f"[WorkerMcpSession] Created for worker '{worker_name}' ({worker_id})")

    async def connect_server(self, config: McpServerConfig) -> bool:
        """
        Connect to an MCP server for this worker.
        
        Args:
            config: Server configuration
            
        Returns:
            True if connected successfully
        """
        server_name = config.name

        # Disconnect existing if any
        if server_name in self._stacks:
            await self.disconnect_server(server_name)

        try:
            # Handle authentication
            auth_headers = {}
            if config.auth_type.value != "none" and config.auth_config:
                handler = mcp_auth_manager.create_handler(server_name, config.auth_config)
                if handler:
                    logger.info(f"[WorkerMcp] Authenticating {self.worker_name} with {server_name}")
                    token = await mcp_auth_manager.authenticate(server_name)
                    auth_headers = mcp_auth_manager.get_headers(server_name)

            # Merge auth headers
            if auth_headers:
                config.headers.update(auth_headers)

            # Create transport and session
            stack = AsyncExitStack()
            try:
                read, write = await stack.enter_async_context(
                    self._transport.create_transport(config)
                )
                session = await self._transport.create_session(read, write)

                self._stacks[server_name] = stack
                self._sessions[server_name] = session
                self._configs[server_name] = config
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                await stack.aclose()
                raise

            # Initialize features
            tools_feature = McpToolsFeature()
            await tools_feature.initialize(session, server_name)
            self._tools_feature[server_name] = tools_feature

            resources_feature = McpResourcesFeature()
            await resources_feature.initialize(session, server_name)
            self._resources_feature[server_name] = resources_feature

            prompts_feature = McpPromptsFeature()
            await prompts_feature.initialize(session, server_name)
            self._prompts_feature[server_name] = prompts_feature

            tools_count = len(tools_feature.get_tools())
            logger.info(
                f"[WorkerMcp] {self.worker_name} connected to {server_name} "
                f"({tools_count} tools)"
            )

            return True

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[WorkerMcp] {self.worker_name} failed to connect to {server_name}: {e}")
            if 'stack' in locals():
                await stack.aclose()
            return False

    async def connect_servers(self, configs: list[McpServerConfig]) -> dict[str, bool]:
        """
        Connect to multiple MCP servers.
        
        Args:
            configs: List of server configurations
            
        Returns:
            Dict of server_name -> success status
        """
        results = {}
        for config in configs:
            success = await self.connect_server(config)
            results[config.name] = success
        return results

    async def disconnect_server(self, server_name: str) -> None:
        """Disconnect a single server."""
        if server_name in self._stacks:
            try:
                await self._stacks[server_name].aclose()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug(f"[WorkerMcp] Error closing stack for '{server_name}': {e}")
            del self._stacks[server_name]

        self._sessions.pop(server_name, None)
        self._configs.pop(server_name, None)
        self._tools_feature.pop(server_name, None)
        self._resources_feature.pop(server_name, None)
        self._prompts_feature.pop(server_name, None)
        self._health_checker.reset(server_name)

        logger.debug(f"[WorkerMcp] {self.worker_name} disconnected from {server_name}")

    async def disconnect_all(self) -> None:
        """Disconnect all servers."""
        for name in list(self._stacks.keys()):
            await self.disconnect_server(name)

        logger.info(f"[WorkerMcp] {self.worker_name} disconnected from all MCP servers")

    def get_tools(self) -> list[EvoLoopTool]:
        """Get all tools from all connected servers."""
        all_tools = []
        for feature in self._tools_feature.values():
            all_tools.extend(feature.get_tools())
        return all_tools

    def get_tools_for(self, server_name: str) -> list[EvoLoopTool]:
        """Get tools for a specific server."""
        feature = self._tools_feature.get(server_name)
        return feature.get_tools() if feature else []

    async def list_resources(self, server_name: str) -> list[dict[str, Any]]:
        """List resources from a server."""
        feature = self._resources_feature.get(server_name)
        if not feature:
            return []

        resources = feature.get_resources()
        return [
            {
                "uri": r.uri,
                "name": r.name,
                "mimeType": r.mimeType,
                "description": r.description,
            }
            for r in resources
        ]

    async def read_resource(self, server_name: str, uri: str) -> McpResourceContent:
        """Read a resource from a server."""
        feature = self._resources_feature.get(server_name)
        if not feature:
            raise RuntimeError(f"Server '{server_name}' not connected")
        return await feature.read_resource(uri)

    async def list_prompts(self, server_name: str) -> list[dict[str, Any]]:
        """List prompts from a server."""
        feature = self._prompts_feature.get(server_name)
        if not feature:
            return []

        prompts = feature.get_prompts()
        return [
            {
                "name": p.name,
                "description": p.description,
            }
            for p in prompts
        ]

    async def get_prompt(self, server_name: str, prompt_name: str, arguments: dict | None = None) -> McpPromptResult:
        """Get a prompt from a server."""
        feature = self._prompts_feature.get(server_name)
        if not feature:
            raise RuntimeError(f"Server '{server_name}' not connected")
        return await feature.get_prompt(prompt_name, arguments)

    def get_connection_summary(self) -> dict[str, Any]:
        """Get summary of all connections."""
        return {
            "worker_id": self.worker_id,
            "worker_name": self.worker_name,
            "connected_servers": list(self._sessions.keys()),
            "tools_count": sum(len(f.get_tools()) for f in self._tools_feature.values()),
            "resources_count": sum(len(f.get_resources()) for f in self._resources_feature.values()),
            "prompts_count": sum(len(f.get_prompts()) for f in self._prompts_feature.values()),
        }


class WorkerMcpManager:
    """
    Manages MCP sessions for Workers.
    
    Creates and tracks isolated MCP sessions per Worker instance.
    """

    def __init__(self):
        self._sessions: dict[str, WorkerMcpSession] = {}

    def create_session(self, worker_id: str, worker_name: str) -> WorkerMcpSession:
        """
        Create a new MCP session for a Worker.
        
        Args:
            worker_id: Unique worker instance ID
            worker_name: Worker role name
            
        Returns:
            WorkerMcpSession instance
        """
        # Clean up existing session if any
        if worker_id in self._sessions:
            logger.warning(f"[WorkerMcpManager] Session already exists for {worker_id}, cleaning up...")
            # Don't await here, just remove reference
            self._sessions.pop(worker_id, None)

        session = WorkerMcpSession(worker_id, worker_name)
        self._sessions[worker_id] = session
        return session

    def get_session(self, worker_id: str) -> WorkerMcpSession | None:
        """Get existing session for a Worker."""
        return self._sessions.get(worker_id)

    async def cleanup_session(self, worker_id: str) -> None:
        """Clean up a Worker's MCP session."""
        session = self._sessions.pop(worker_id, None)
        if session:
            await session.disconnect_all()
            logger.info(f"[WorkerMcpManager] Cleaned up session for {worker_id}")

    async def cleanup_all(self) -> None:
        """Clean up all Worker MCP sessions."""
        worker_ids = list(self._sessions.keys())
        for worker_id in worker_ids:
            await self.cleanup_session(worker_id)

    def get_active_sessions(self) -> list[dict[str, Any]]:
        """Get summary of all active sessions."""
        return [session.get_connection_summary() for session in self._sessions.values()]


# Global instance
worker_mcp_manager = WorkerMcpManager()
