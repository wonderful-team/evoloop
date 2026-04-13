"""MCP Client Manager - manages connections to external MCP servers."""

import json
import logging
import os
from contextlib import AsyncExitStack
from typing import Any, Optional
from pydantic import BaseModel, Field

from langchain_core.tools import StructuredTool
from sqlalchemy import select

from app.core.mcp.auth.manager import mcp_auth_manager
from app.core.mcp.config import AuthType, McpServerConfig, TransportType, ConnectionResult, ConnectionState
from app.core.mcp.features.base import McpPromptResult, McpResourceContent
from app.core.mcp.features.prompts import McpPromptsFeature
from app.core.mcp.features.resources import McpResourcesFeature
from app.core.mcp.features.tools import McpToolsFeature
from app.core.mcp.health import McpHealthChecker, HealthStatus
from app.core.mcp.transport import McpTransport
from app.infrastructure.database.sql.database import session_scope
from app.models import McpServer
from app.utils.model_helpers import LegacyDictMixin


class McpResource(BaseModel, LegacyDictMixin):
    uri: str
    name: str
    mimeType: str | None = None
    description: str | None = None


class McpPromptArgument(BaseModel, LegacyDictMixin):
    name: str
    required: bool = False


class McpPrompt(BaseModel, LegacyDictMixin):
    name: str
    description: str | None = None
    arguments: list[McpPromptArgument] = Field(default_factory=list)


class McpServerSummary(BaseModel, LegacyDictMixin):
    name: str
    command: str | None = None
    status: str
    tools_count: int
    enabled: bool



logger = logging.getLogger(__name__)


class McpClientManager:
    """
    Manages connections to external MCP servers and exposes their capabilities.
    
    Responsibilities:
    - Connection lifecycle management (connect/disconnect/reconnect)
    - Health checking and auto-reconnection
    - Tool caching and conversion
    - Configuration persistence (DB integration)
    
    Architecture:
        ┌─────────────────────────────────┐
        │      McpClientManager           │
        ├─────────────────────────────────┤
        │  ┌──────────┐  ┌─────────────┐ │
        │  │ Transport│  │HealthChecker│ │
        │  └──────────┘  └─────────────┘ │
        ├─────────────────────────────────┤
        │  ┌────────────────────────────┐ │
        │  │     Features (Tools)       │ │
        │  └────────────────────────────┘ │
        └─────────────────────────────────┘
    """
    
    def __init__(self):
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
        
        # Legacy migration
        self._legacy_config_path = "mcp_servers_config.json"
    
    # ═══════════════════════════════════════════════════════════
    # Connection Lifecycle
    # ═══════════════════════════════════════════════════════════
    
    async def connect(self, config: McpServerConfig) -> ConnectionResult:
        """
        Connect to an MCP server.
        
        Args:
            config: Server configuration
            
        Returns:
            ConnectionResult with success status and tool count
        """
        config.validate()
        server_name = config.name
        
        # Disconnect existing if any
        if server_name in self._stacks:
            await self.disconnect(server_name)
        
        try:
            # Handle OAuth authentication if configured
            auth_headers = {}
            if config.auth_type != AuthType.NONE and config.auth_config:
                handler = mcp_auth_manager.create_handler(server_name, config.auth_config)
                if handler:
                    logger.info(f"Authenticating with {server_name} using {config.auth_type}")
                    token = await mcp_auth_manager.authenticate(server_name)
                    auth_headers = mcp_auth_manager.get_headers(server_name)
                    logger.info(f"Successfully authenticated with {server_name}")
            
            # Merge auth headers into config headers
            if auth_headers:
                config.headers.update(auth_headers)
            
            # Create transport and session
            stack = AsyncExitStack()
            
            async with self._transport.create_transport(config) as (read, write):
                session = await self._transport.create_session(read, write)
                
                # Keep stack open by moving it to instance
                self._stacks[server_name] = stack
                self._sessions[server_name] = session
                self._configs[server_name] = config
            
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
            resources_count = len(resources_feature.get_resources())
            prompts_count = len(prompts_feature.get_prompts())
            
            logger.info(
                f"Connected to MCP server: {server_name} "
                f"({tools_count} tools, {resources_count} resources, {prompts_count} prompts)"
            )
            
            return ConnectionResult(
                success=True,
                server_name=server_name,
                tools_count=tools_count
            )
            
        except Exception as e:
            logger.error(f"Error connecting to {server_name}: {e}")
            if 'stack' in locals():
                await stack.aclose()
            return ConnectionResult(
                success=False,
                server_name=server_name,
                error=str(e)
            )
    
    async def connect_from_db(self, server_name: str) -> ConnectionResult:
        """
        Connect to a server using configuration from database.
        
        Args:
            server_name: Name of server in database
            
        Returns:
            ConnectionResult
        """
        async with session_scope() as session:
            result = await session.execute(
                select(McpServer).where(
                    McpServer.name == server_name,
                    McpServer.enabled
                )
            )
            server = result.scalars().first()
            
            if not server:
                return ConnectionResult(
                    success=False,
                    server_name=server_name,
                    error=f"Server '{server_name}' not found in database or disabled"
                )
            
            # Parse args and env
            args = self._parse_json_field(server.args, [])
            env = self._parse_json_field(server.env, {})
            
            # Determine transport type
            transport = TransportType.SSE if (
                server.command and (
                    server.command.startswith("http://") or 
                    server.command.startswith("https://")
                )
            ) else TransportType.STDIO
            
            config = McpServerConfig(
                name=server.name,
                transport=transport,
                command=server.command,
                args=args,
                env=env,
                enabled=server.enabled
            )
            
            return await self.connect(config)
    
    async def connect_all(self) -> list[ConnectionResult]:
        """
        Connect to all enabled servers from database.
        Also handles legacy config migration.
        
        Returns:
            List of connection results
        """
        results = []
        
        # 1. Migrate legacy config if needed
        await self._seed_legacy_config()
        
        # 2. Fetch and connect all enabled servers
        async with session_scope() as session:
            result = await session.execute(
                select(McpServer).where(McpServer.enabled)
            )
            servers = result.scalars().all()
            
            for server in servers:
                try:
                    result = await self.connect_from_db(server.name)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to connect to MCP server '{server.name}': {e}")
                    results.append(ConnectionResult(
                        success=False,
                        server_name=server.name,
                        error=str(e)
                    ))
        
        # Check critical servers
        if "filesystem" not in self._sessions:
            logger.critical("CRITICAL: 'filesystem' MCP server failed to connect!")
        
        return results
    
    async def disconnect(self, server_name: str) -> None:
        """Disconnect a single server."""
        if server_name in self._stacks:
            try:
                await self._stacks[server_name].aclose()
            except Exception as e:
                logger.debug(f"Error closing stack for '{server_name}': {e}")
            del self._stacks[server_name]
        
        self._sessions.pop(server_name, None)
        self._configs.pop(server_name, None)
        self._tools_feature.pop(server_name, None)
        self._resources_feature.pop(server_name, None)
        self._prompts_feature.pop(server_name, None)
        self._health_checker.reset(server_name)
        
        logger.info(f"Disconnected MCP server: {server_name}")
    
    async def disconnect_all(self) -> None:
        """Disconnect all servers."""
        for name in list(self._stacks.keys()):
            await self.disconnect(name)
    
    async def cleanup(self) -> None:
        """Alias for disconnect_all (for backward compatibility)."""
        await self.disconnect_all()
    
    # ═══════════════════════════════════════════════════════════
    # Health & Reconnection
    # ═══════════════════════════════════════════════════════════
    
    async def health_check(self, server_name: str) -> HealthStatus:
        """Check health of a server."""
        session = self._sessions.get(server_name)
        return await self._health_checker.check(server_name, session)
    
    async def ensure_connected(self, server_name: str) -> bool:
        """
        Ensure server is connected, reconnect if necessary.
        
        Args:
            server_name: Server to check/connect
            
        Returns:
            True if connected after this call
        """
        # Check existing connection
        if server_name in self._sessions:
            health = await self.health_check(server_name)
            if health.is_healthy:
                return True
            logger.info(f"Stale session for '{server_name}', reconnecting...")
            await self.disconnect(server_name)
        
        # Try reconnect from cached config
        if server_name in self._configs:
            result = await self.connect(self._configs[server_name])
            return result.success
        
        # Try load from DB
        result = await self.connect_from_db(server_name)
        return result.success
    
    # ═══════════════════════════════════════════════════════════
    # Tool Access
    # ═══════════════════════════════════════════════════════════
    
    @property
    def sessions(self) -> dict[str, Any]:
        """Access sessions dict (for backward compatibility)."""
        return self._sessions
    
    @property
    def _server_configs(self) -> dict[str, McpServerConfig]:
        """Access configs (for backward compatibility)."""
        return self._configs
    
    async def get_tools(self, server_name: str | None = None) -> list[StructuredTool]:
        """
        Get tools for a specific server, or all tools if no server specified.
        
        Args:
            server_name: Server name (optional, None = get all)
            
        Returns:
            List of LangChain tools
        """
        if server_name is None:
            # Return all tools from all connected servers
            return self.get_all_tools()
        
        if await self.ensure_connected(server_name):
            feature = self._tools_feature.get(server_name)
            if feature:
                return feature.get_tools()
        return []
    
    def get_all_tools(self) -> list[StructuredTool]:
        """Get all tools from all connected servers."""
        all_tools = []
        for feature in self._tools_feature.values():
            all_tools.extend(feature.get_tools())
        return all_tools
    
    # ═══════════════════════════════════════════════════════════
    # Resources Access
    # ═══════════════════════════════════════════════════════════
    
    async def list_resources(self, server_name: str) -> list[McpResource]:
        """
        List available resources from a server.
        
        Args:
            server_name: Server name
            
        Returns:
            List of resource info dicts
        """
        if await self.ensure_connected(server_name):
            feature = self._resources_feature.get(server_name)
            if feature:
                resources = feature.get_resources()
                return [
                    McpResource(
                        uri=r.uri,
                        name=r.name,
                        mimeType=r.mimeType,
                        description=r.description,
                    )
                    for r in resources
                ]
        return []
    
    async def read_resource(self, server_name: str, uri: str) -> McpResourceContent:
        """
        Read content from a resource URI.
        
        Args:
            server_name: Server name
            uri: Resource URI to read
            
        Returns:
            Dict with content and metadata
        """
        if await self.ensure_connected(server_name):
            feature = self._resources_feature.get(server_name)
            if feature:
                return await feature.read_resource(uri)
        raise RuntimeError(f"Server '{server_name}' not connected or resources not available")
    
    def get_resources_formatted(self, server_name: str) -> str:
        """
        Get formatted markdown list of resources.
        
        Args:
            server_name: Server name
            
        Returns:
            Markdown formatted string
        """
        feature = self._resources_feature.get(server_name)
        if feature:
            return feature.format_resources_list()
        return "*Server not connected*"
    
    # ═══════════════════════════════════════════════════════════
    # Prompts Access
    # ═══════════════════════════════════════════════════════════
    
    async def list_prompts(self, server_name: str) -> list[McpPrompt]:
        """
        List available prompts from a server.
        
        Args:
            server_name: Server name
            
        Returns:
            List of prompt info dicts
        """
        if await self.ensure_connected(server_name):
            feature = self._prompts_feature.get(server_name)
            if feature:
                prompts = feature.get_prompts()
                return [
                    McpPrompt(
                        name=p.name,
                        description=p.description,
                        arguments=[
                            McpPromptArgument(name=arg.name, required=arg.required)
                            for arg in (p.arguments or [])
                        ],
                    )
                    for p in prompts
                ]
        return []
    
    async def get_prompt(
        self, 
        server_name: str, 
        prompt_name: str, 
        arguments: dict[str, str] | None = None
    ) -> McpPromptResult:
        """
        Get a rendered prompt with optional arguments.
        
        Args:
            server_name: Server name
            prompt_name: Prompt name
            arguments: Optional arguments for the prompt
            
        Returns:
            Dict with prompt messages and metadata
        """
        if await self.ensure_connected(server_name):
            feature = self._prompts_feature.get(server_name)
            if feature:
                return await feature.get_prompt(prompt_name, arguments)
        raise RuntimeError(f"Server '{server_name}' not connected or prompts not available")
    
    def get_prompts_formatted(self, server_name: str) -> str:
        """
        Get formatted markdown list of prompts.
        
        Args:
            server_name: Server name
            
        Returns:
            Markdown formatted string
        """
        feature = self._prompts_feature.get(server_name)
        if feature:
            return feature.format_prompts_list()
        return "*Server not connected*"
    
    # ═══════════════════════════════════════════════════════════
    # Server Management
    # ═══════════════════════════════════════════════════════════
    
    async def add_server(self, name: str, details: dict[str, Any]) -> ConnectionResult:
        """Add server to DB and connect."""
        # Update DB
        async with session_scope() as session:
            result = await session.execute(
                select(McpServer).where(McpServer.name == name)
            )
            db_server = result.scalars().first()
            
            args_json = json.dumps(details.get("args", []))
            env_json = json.dumps(details.get("env", {}))
            
            if db_server:
                db_server.command = details.get("command")
                db_server.args = args_json
                db_server.env = env_json
                db_server.enabled = True
            else:
                db_server = McpServer(
                    name=name,
                    command=details.get("command"),
                    args=args_json,
                    env=env_json,
                    enabled=True
                )
                session.add(db_server)
        
        # Connect
        transport = TransportType.SSE if (
            details.get("command", "").startswith(("http://", "https://"))
        ) else TransportType.STDIO
        
        config = McpServerConfig(
            name=name,
            transport=transport,
            command=details.get("command"),
            args=details.get("args", []),
            env=details.get("env", {}),
            enabled=True
        )
        
        return await self.connect(config)
    
    async def remove_server(self, name: str) -> bool:
        """Remove server from DB and disconnect."""
        await self.disconnect(name)
        
        async with session_scope() as session:
            result = await session.execute(
                select(McpServer).where(McpServer.name == name)
            )
            server = result.scalars().first()
            if server:
                await session.delete(server)
                return True
        return False
    
    async def list_servers(self) -> list[McpServerSummary]:
        """List all servers with status."""
        async with session_scope() as session:
            result = await session.execute(select(McpServer))
            servers = result.scalars().all()
            
            output = []
            for s in servers:
                is_connected = s.name in self._sessions
                feature = self._tools_feature.get(s.name)
                tools_count = len(feature.get_tools()) if feature else 0
                
                output.append(McpServerSummary(
                    name=s.name,
                    command=s.command,
                    status="connected" if is_connected else "available",
                    tools_count=tools_count,
                    enabled=s.enabled
                ))
            return output
    
    def get_connection_state(self, server_name: str) -> ConnectionState:
        """Get current connection state for a server."""
        is_connected = server_name in self._sessions
        feature = self._tools_feature.get(server_name)
        
        return ConnectionState(
            server_name=server_name,
            is_connected=is_connected,
            last_health_check=self._health_checker.get_last_check_time(server_name),
            tools_count=len(feature.get_tools()) if feature else 0
        )
    
    # ═══════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════
    
    async def _seed_legacy_config(self) -> None:
        """Migrate legacy JSON config to database."""
        async with session_scope() as session:
            result = await session.execute(select(McpServer))
            if result.first() is not None:
                return
            
            if not os.path.exists(self._legacy_config_path):
                return
            
            logger.info("Migrating legacy MCP config to database...")
            try:
                with open(self._legacy_config_path, encoding="utf-8") as f:
                    config = json.load(f)
                    servers = config.get("mcpServers", {})
                    
                    for name, details in servers.items():
                        new_server = McpServer(
                            name=name,
                            command=details.get("command"),
                            args=json.dumps(details.get("args", [])),
                            env=json.dumps(details.get("env", {})),
                            enabled=True
                        )
                        session.add(new_server)
                logger.info("Legacy MCP config migrated successfully.")
            except Exception as e:
                logger.error(f"Failed to migrate legacy config: {e}")
    
    @staticmethod
    def _parse_json_field(value: Any, default: Any) -> Any:
        """Parse JSON string field."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return default
        return value if value is not None else default


# Singleton instance
mcp_client_manager = McpClientManager()
