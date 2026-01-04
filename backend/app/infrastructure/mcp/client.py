import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack
from typing import Dict, List, Any, Optional

from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import McpServer

import sys
from contextlib import contextmanager

@contextmanager
def restore_std_streams():
    """
    Temporarily restore sys.stdout and sys.stderr to original streams.
    This fixes issues where libraries (like Celery) monkey-patch stdout/stderr with proxies
    that don't implement fileno(), causing subprocess creation to fail.
    """
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    
    try:
        if hasattr(sys, '__stdout__') and sys.__stdout__:
            sys.stdout = sys.__stdout__
        if hasattr(sys, '__stderr__') and sys.__stderr__:
            sys.stderr = sys.__stderr__
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

logger = logging.getLogger("evoloop.mcp_client")


class McpClientManager:
    """
    Manages connections to external MCP servers and exposes their tools to LangChain agents.
    Persists configuration in Postgres database.
    """

    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self._tools_cache: Dict[str, List[StructuredTool]] = {}
        # Legacy config path for migration
        self.legacy_config_path = "mcp_servers_config.json"

    async def _seed_legacy_config(self):
        """One-time migration: Import JSON config to DB if DB is empty."""
        async with session_scope() as session:
            # Check if empty
            result = await session.execute(select(McpServer))
            if result.first() is not None:
                return

            if not os.path.exists(self.legacy_config_path):
                return

            logger.info("Migrating legacy MCP config to Database...")
            try:
                with open(self.legacy_config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    servers = config.get("mcpServers", {})
                    
                    for name, details in servers.items():
                        new_server = McpServer(
                            name=name,
                            command=details.get("command"),
                            args=details.get("args", []),
                            env=details.get("env", {})
                        )
                        session.add(new_server)
                logger.info("Legacy MCP config migrated successfully.")
            except Exception as e:
                logger.error(f"Failed to migrate legacy config: {e}")
                # Don't raise, just skip

    async def connect_all(self):
        """Connect to all enabled servers from DB."""
        # 1. Try Seed
        await self._seed_legacy_config()

        # 2. Fetch from DB
        async with session_scope() as session:
            result = await session.execute(select(McpServer).where(McpServer.enabled == True))
            servers = result.scalars().all()

            for server in servers:
                try:
                    # Convert Pydantic/SQLAlchemy models to dict args if needed
                    # Stored as JSON strings in DB? 
                    # Wait, in models.py I defined them as Mapped[List[str]] = mapped_column(Text).
                    # SQLAlchemy doesn't auto-json-parse Text columns unless we use specific types or TypeDecorators.
                    # BUT, SQLModel/Pydantic might handle it if using JSON column type. 
                    # Postgres has JSONB. In models.py I used `Text` for args/env. 
                    # I need to parse them manually here if they are strings.
                    
                    # Correction: In models.py step 1031:
                    # args: Mapped[List[str]] = mapped_column(Text)
                    # env: Mapped[dict] = mapped_column(Text)
                    # This implies I need to JSON load them if they come back as strings.
                    # Or use `JSON` type in SQLAlchemy.
                    # For safety, I will try to parse them if they are strings.
                    
                    cmd_args = server.args
                    if isinstance(cmd_args, str):
                        try:
                            cmd_args = json.loads(cmd_args)
                        except:
                            cmd_args = []
                            
                    cmd_env = server.env
                    if isinstance(cmd_env, str):
                        try:
                            cmd_env = json.loads(cmd_env)
                        except:
                            cmd_env = {}

                    details = {
                        "command": server.command,
                        "args": cmd_args,
                        "env": cmd_env
                    }
                    await self.connect_server(server.name, details)
                except Exception as e:
                    logger.error(f"Failed to connect to MCP server '{server.name}': {e}")

        # Post-Connect Health Check
        if "filesystem" not in self.sessions:
             logger.critical("CRITICAL: 'filesystem' MCP server failed to connect! Agent will be unable to edit files.")
             # Optionally raise system exit or set a global health flag?
             # For now, distinct log is enough for monitoring.

    async def connect_server(self, name: str, details: Dict[str, Any]):
        """Connect to a single MCP server (Stdio only for now)."""
        logger.info(f"Connecting to MCP server: {name}")
        
        command = details.get("command")
        args = details.get("args", [])
        env = details.get("env", {})

        # Merge current env with provided env
        full_env = os.environ.copy()
        full_env.update(env)

        if not command:
            logger.error(f"Server '{name}' missing 'command'.")
            return

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=full_env
        )





        try:
            # Enter the context managers
            # Use restore_std_streams to avoid 'LoggingProxy' errors during subprocess spawn
            with restore_std_streams():
                read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
            
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            
            await session.initialize()
            self.sessions[name] = session
            logger.info(f"Connected to MCP server: {name}")
            
            # Pre-fetch tools
            await self._refresh_tools(name)
            
        except Exception as e:
            logger.error(f"Error connecting to {name}: {e}")
            raise

    async def _refresh_tools(self, server_name: str):
        """Fetch tools from a connected server and convert to LangChain tools."""
        session = self.sessions.get(server_name)
        if not session:
            return

        try:
            result = await session.list_tools()
            lc_tools = []

            for tool in result.tools:
                async def _tool_func(*args, **kwargs):
                    return await session.call_tool(tool.name, arguments=kwargs)

                args_schema = self._create_args_schema(tool.name, tool.inputSchema)

                lc_tool = StructuredTool.from_function(
                    func=None,
                    coroutine=_tool_func,
                    name=tool.name,
                    description=tool.description or "",
                    args_schema=args_schema
                )
                
                lc_tools.append(lc_tool)

            self._tools_cache[server_name] = lc_tools
            logger.info(f"Loaded {len(lc_tools)} tools from {server_name}")

        except Exception as e:
            logger.error(f"Failed to list tools for {server_name}: {e}")

    def _create_args_schema(self, tool_name: str, schema: Dict[str, Any]):
        """Dynamically create a Pydantic model from a JSON schema."""
        from pydantic import create_model, Field

        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None)
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
                fields[field_name] = (Optional[field_type], Field(default=None, description=description))

        model_name = f"{tool_name}Input"
        return create_model(model_name, **fields)

    def get_tools(self) -> List[StructuredTool]:
        """Get all loaded tools from all servers."""
        all_tools = []
        for tools in self._tools_cache.values():
            all_tools.extend(tools)
        return all_tools

    async def cleanup(self):
        """Disconnect all servers."""
        await self.exit_stack.aclose()

    async def add_server(self, name: str, details: Dict[str, Any]):
        """Add a new server to DB and connect."""
        if name in self.sessions:
            logger.warning(f"Server {name} already runnning. Updating...")

        # 1. Update DB
        async with session_scope() as session:
            # Check if exists
            result = await session.execute(select(McpServer).where(McpServer.name == name))
            server = result.scalars().first()
            
            # Serialize
            args_json = json.dumps(details.get("args", []))
            env_json = json.dumps(details.get("env", {}))
            
            if server:
                server.command = details.get("command")
                server.args = args_json
                server.env = env_json
                server.enabled = True
            else:
                server = McpServer(
                    name=name,
                    command=details.get("command"),
                    args=args_json,
                    env=env_json,
                    enabled=True
                )
                session.add(server)
            
            # Commit happens automatically in session_scope

        # 2. Connect (Live update)
        # If it was connected, we might want to reconnect to refresh tools/config?
        # TODO: Implement disconnect logic if exists
        await self.connect_server(name, details)
        return {"status": "connected", "tools": len(self._tools_cache.get(name, []))}

    async def remove_server(self, name: str):
        """Remove a server from DB and disconnect."""
        # 1. Disconnect Logic (Incomplete in legacy, but we can try to clean up memory)
        if name in self.sessions:
             del self.sessions[name]
             if name in self._tools_cache:
                 del self._tools_cache[name]
        
        # 2. Remove from DB
        async with session_scope() as session:
            result = await session.execute(select(McpServer).where(McpServer.name == name))
            server = result.scalars().first()
            if server:
                await session.delete(server)
                
        return True

    async def list_servers(self) -> List[Dict[str, Any]]:
        """List servers from DB, enriched with connection status."""
        async with session_scope() as session:
            result = await session.execute(select(McpServer))
            servers = result.scalars().all()
            
            output = []
            for s in servers:
                is_connected = s.name in self.sessions
                output.append({
                    "name": s.name,
                    "command": s.command,
                    "status": "connected" if is_connected else "disconnected",
                    "tools_count": len(self._tools_cache.get(s.name, [])) if is_connected else 0
                })
            return output

# Singleton instance
mcp_client_manager = McpClientManager()
