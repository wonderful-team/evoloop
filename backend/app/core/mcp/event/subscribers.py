"""
MCP (Model Context Protocol) Module Lifecycle Handlers
Handles connection initialization and global client cleanup.
"""
import json
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe
from app.infrastructure.config import SystemConfigService
from app.infrastructure.database import session_scope
from app.models import McpServer

logger = logging.getLogger(__name__)


@event_register()
class McpLifecycleSubscriber:
    """
    Handles initialization and graceful shutdown of MCP clients.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Initialize/Register configured MCP servers.
        """
        logger.info("[MCP] 🔌 Initializing MCP Servers...")
        mcp_results = await init_mcp()
        logger.info(f"[MCP] ✓ Servers initialized: {len(mcp_results)}")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        """
        Handle APP_STOPPING: Disconnect and cleanup all active MCP clients.
        """
        try:
            from app.core.mcp import mcp_client_manager
            await mcp_client_manager.disconnect_all()
            logger.info("[MCP] All clients disconnected")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[MCP] Cleanup failed: {e}")

    @event_subscribe(SystemEventType.CONFIG_CHANGED)
    async def on_config_changed(self, event):
        """
        Handle CONFIG_CHANGED: Respond to configuration updates.
        """
        key = event.data.get("key")
        new_value = event.data.get("new_value")
        
        if key == "WORKSPACE_ROOT":
            logger.info(f"[MCP] WORKSPACE_ROOT changed to {new_value}, reloading filesystem MCP...")
            await reload_mcp_for_workspace_change()


async def init_mcp(force_update: bool = False) -> dict[str, str]:
    """
    Initialize MCP server configurations.

    This function ONLY adds server configs to DB, it does NOT connect.
    Connection happens later via mcp_client_manager.connect_all().

    Args:
        force_update: If True, reconfigure filesystem even if already configured
                     (useful when WORKSPACE_ROOT changes)

    Returns:
        Dict of configured server names and their status ("added", "skipped", "error")
    """
    logger.info("Initializing MCP configuration...")
    results = {}

    # Check existing servers in DB (not connected sessions)
    async with session_scope() as session:
        result = await session.execute(select(McpServer.name))
        existing_db_servers = {row[0] for row in result.all()}

    # Use the SQLAlchemy URI from settings
    db_url = str(settings.SQLALCHEMY_DATABASE_URI)

    # 1. Local Postgres (System Default)
    if "local-postgres" not in existing_db_servers:
        details_pg = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres", db_url],
            "env": {},
        }
        try:
            await _add_mcp_server_to_db("local-postgres", details_pg)
            logger.info("MCP 'local-postgres' added to DB.")
            results["local-postgres"] = "added"
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"Failed to add local-postgres to DB: {e}")
            results["local-postgres"] = "error"
    else:
        logger.debug("MCP 'local-postgres' already in DB, skipping.")
        results["local-postgres"] = "skipped"

    # 2. Filesystem (Critical for Coder)
    workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
    if workspace_root:
        needs_update = force_update
        needs_add = "filesystem" not in existing_db_servers

        # Check for path mismatch to trigger update automatically
        if not needs_add and not needs_update:
            async with session_scope() as session:
                result = await session.execute(
                    select(McpServer).where(McpServer.name == "filesystem")
                )
                fs_server = result.scalars().first()
                if fs_server:
                    current_args = json.loads(fs_server.args)
                    # MCP args usually look like ["-y", "@...", "/path"] or just ["/path"]
                    # We just check if workspace_root is present in any of the args
                    if workspace_root not in current_args:
                        logger.info(f"Path mismatch detected for filesystem MCP: {workspace_root} not in {current_args}")
                        needs_update = True

        if needs_update:
            # Remove from DB first, will be re-added with new config
            logger.info("Updating filesystem MCP in DB due to WORKSPACE_ROOT change...")
            try:
                async with session_scope() as session:
                    result = await session.execute(
                        select(McpServer).where(McpServer.name == "filesystem")
                    )
                    server = result.scalars().first()
                    if server:
                        await session.delete(server)
                existing_db_servers.discard("filesystem")
                needs_add = True
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"Error removing existing filesystem MCP from DB: {e}")

        if needs_add:
            fs_args = [workspace_root]
            details_fs = {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", *fs_args],
                "env": {},
            }
            try:
                await _add_mcp_server_to_db("filesystem", details_fs)
                logger.info(f"MCP 'filesystem' added to DB for {workspace_root}.")
                results["filesystem"] = "added"
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"Failed to add filesystem to DB: {e}")
                results["filesystem"] = "error"
        else:
            logger.debug("MCP 'filesystem' already in DB, skipping.")
            results["filesystem"] = "skipped"
    else:
        logger.warning("WORKSPACE_ROOT not configured. Skipping MCP 'filesystem'.")
        results["filesystem"] = "skipped_no_workspace"

    # 3. Brave Search (Network Capability)
    brave_key = settings.BRAVE_API_KEY
    if brave_key:
        if "brave-search" not in existing_db_servers:
            details_brave = {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                "env": {"BRAVE_API_KEY": brave_key},
            }
            try:
                await _add_mcp_server_to_db("brave-search", details_brave)
                logger.info("MCP 'brave-search' added to DB.")
                results["brave-search"] = "added"
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"Failed to add brave-search to DB: {e}")
                results["brave-search"] = "error"
        else:
            logger.debug("MCP 'brave-search' already in DB, skipping.")
            results["brave-search"] = "skipped"
    else:
        logger.debug("BRAVE_API_KEY not found. Skipping 'brave-search'.")
        results["brave-search"] = "skipped_no_key"

    return results


async def reload_mcp_for_workspace_change() -> dict[str, str]:
    """
    Reconfigure MCP servers when WORKSPACE_ROOT changes at runtime.

    Only filesystem MCP needs to be reconfigured.

    Returns:
        Dict of server names and their status
    """
    logger.info("Reloading MCP configuration due to WORKSPACE_ROOT change...")
    results = {}

    # 1. Update DB config (init_mcp handles path check and DB update)
    db_result = await init_mcp(force_update=True)
    results["db_update"] = db_result

    # 2. Disconnect and reconnect filesystem MCP
    try:
        from app.core.mcp import mcp_client_manager

        # Disconnect existing if connected
        if "filesystem" in mcp_client_manager.sessions:
            logger.info("Disconnecting existing filesystem MCP...")
            # remove_server handles both disconnect and cleanup
            await mcp_client_manager.remove_server("filesystem")
            results["disconnect"] = "success"
        else:
            results["disconnect"] = "not_connected"

        # Reconnect (will load new config from DB)
        logger.info("Reconnecting filesystem MCP...")
        connected = await mcp_client_manager.ensure_connected("filesystem")
        results["reconnect"] = "success" if connected else "failed"

    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Failed to reload MCP for workspace change: {e}")
        results["error"] = str(e)

    return results


async def _add_mcp_server_to_db(name: str, details: dict) -> None:
    """Add MCP server configuration to DB without connecting."""
    async with session_scope() as session:
        args_json = json.dumps(details.get("args", []))
        env_json = json.dumps(details.get("env", {}))

        server = McpServer(
            name=name,
            command=details.get("command"),
            args=args_json,
            env=env_json,
            enabled=True,
        )
        session.add(server)
