import asyncio
import json
import logging
import os

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine, init_db
from app.infrastructure.config import SystemConfigService
from app.infrastructure.database.sql.database import session_scope
from app.models import McpServer

logger = logging.getLogger(__name__)


def init() -> None:
    with Session(engine) as session:
        init_db(session)

    # Seed System Configuration from Environment/Settings
    # This ensures that on first run, the database is populated with valid defaults
    # 1. WORKSPACE_ROOT
    # Only seed from settings if explicitly configured, otherwise leave empty for user to set
    if not SystemConfigService.get_value("WORKSPACE_ROOT"):
        default_root = settings.WORKSPACE_ROOT
        if default_root:
            logger.info(f"Seeding WORKSPACE_ROOT from settings: {default_root}")
            SystemConfigService.set_value("WORKSPACE_ROOT", default_root, "Root directory for workspace/project storage")
        else:
            logger.info("WORKSPACE_ROOT not configured. User will be prompted to set it during initialization.")

    # 2. EVOCLOUD_DEVICE_NAME
    if not SystemConfigService.get_value("EVOCLOUD_DEVICE_NAME"):
        default_name = settings.EVOCLOUD_DEVICE_NAME
        if default_name:
            logger.info(f"Seeding EVOCLOUD_DEVICE_NAME from settings: {default_name}")
            SystemConfigService.set_value("EVOCLOUD_DEVICE_NAME", default_name, "Device identifier for EvoLoop Link")

    # 3. Embedding Configuration
    # Use settings values (which come from .env) instead of hardcoding
    # This allows users to configure via environment variables
    if not SystemConfigService.get_value("EMBEDDING_PROVIDER"):
        logger.info("Seeding Embedding Configuration from settings...")
        SystemConfigService.set_value(
            "EMBEDDING_PROVIDER",
            settings.EMBEDDING_PROVIDER,
            "Embedding Provider (openai, ollama, dashscope, huggingface, local)"
        )
        SystemConfigService.set_value(
            "EMBEDDING_BASE_URL",
            settings.EMBEDDING_BASE_URL or settings.OPENAI_BASE_URL,
            "Embedding Base URL"
        )
        SystemConfigService.set_value(
            "EMBEDDING_MODEL",
            settings.EMBEDDING_MODEL_NAME,
            "Embedding Model Name"
        )
        SystemConfigService.set_value(
            "EMBEDDING_API_KEY",
            settings.OPENAI_API_KEY,
            "Embedding API Key"
        )
        SystemConfigService.set_value(
            "EMBEDDING_DIMENSIONS",
            str(settings.EMBEDDING_DIMENSIONS),
            "Embedding Dimensions"
        )

    # 4. Vision Configuration
    # Use settings.OPENAI_MODEL_NAME as default vision model
    if not SystemConfigService.get_value("VISION_MODEL"):
        default_vision = getattr(settings, 'VISION_MODEL', settings.OPENAI_MODEL_NAME)
        logger.info(f"Seeding VISION_MODEL from settings: {default_vision}")
        SystemConfigService.set_value(
            "VISION_MODEL",
            default_vision,
            "Vision Model Name (Multimodal)"
        )

    # 5. HITL / Router Configuration
    if not SystemConfigService.get_value("INTENT_MIN_CONFIDENCE"):
        logger.info("Seeding INTENT_MIN_CONFIDENCE...")
        SystemConfigService.set_value("INTENT_MIN_CONFIDENCE", "0.35", "Intent Classifier Threshold (0.0-1.0)")

    # 6. LLM Configuration (from settings)
    _seed_llm_config(SystemConfigService)


def _seed_llm_config(SystemConfigService):
    """Seed LLM configuration from settings if not already set."""
    # Only seed if LLM_PROVIDER is not set (first run)
    if not SystemConfigService.get_value("LLM_PROVIDER"):
        logger.info("Seeding LLM Configuration from settings...")

        # Determine provider from settings
        provider = "openai"  # default
        if settings.ANTHROPIC_API_KEY:
            provider = "anthropic"
        elif settings.OPENAI_API_KEY and "localhost" in settings.OPENAI_BASE_URL:
            provider = "ollama"  # or local

        SystemConfigService.set_value("LLM_PROVIDER", provider, "LLM Provider (openai, anthropic, ollama)")
        SystemConfigService.set_value("LLM_BASE_URL", settings.OPENAI_BASE_URL, "LLM API Base URL")
        SystemConfigService.set_value("LLM_MODEL", settings.OPENAI_MODEL_NAME, "LLM Model Name")
        SystemConfigService.set_value("LLM_API_KEY", settings.OPENAI_API_KEY, "LLM API Key")
        
        # Config type: "platform" (use EvoLoop Gateway) or "custom" (use own API key)
        SystemConfigService.set_value("LLM_CONFIG_TYPE", "custom", "LLM Config Type (platform, custom)")

        # Vision model (reuse main model if not specified)
        vision_model = getattr(settings, 'VISION_MODEL', settings.OPENAI_MODEL_NAME)
        SystemConfigService.set_value("VISION_MODEL", vision_model, "Vision Model Name")


async def init_atlas_config() -> None:
    """Initialize Atlas configuration (Cache-based, no hardcoding)."""
    logger.info("Initializing Atlas configuration...")
    from app.core.atlas.config_manager import AtlasConfigManager
    await AtlasConfigManager.initialize_defaults()


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
        except Exception as e:
            logger.error(f"Failed to add local-postgres to DB: {e}")
            results["local-postgres"] = "error"
    else:
        logger.debug("MCP 'local-postgres' already in DB, skipping.")
        results["local-postgres"] = "skipped"

    # 2. Filesystem (Critical for Coder)
    db_workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
    workspace_root = db_workspace_root if db_workspace_root else settings.WORKSPACE_ROOT

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
                    try:
                        current_args = json.loads(fs_server.args)
                        # MCP args usually look like ["-y", "@...", "/path"] or just ["/path"]
                        # We just check if workspace_root is present in any of the args
                        if workspace_root not in current_args:
                            logger.info(f"Path mismatch detected for filesystem MCP: {workspace_root} not in {current_args}")
                            needs_update = True
                    except Exception as e:
                        logger.warning(f"Could not parse filesystem args for mismatch check: {e}")

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
            except Exception as e:
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
            except Exception as e:
                logger.error(f"Failed to add filesystem to DB: {e}")
                results["filesystem"] = "error"
        else:
            logger.debug("MCP 'filesystem' already in DB, skipping.")
            results["filesystem"] = "skipped"
    else:
        logger.warning("WORKSPACE_ROOT not configured. Skipping MCP 'filesystem'.")
        results["filesystem"] = "skipped_no_workspace"

    # 3. Brave Search (Network Capability)
    brave_key = os.getenv("BRAVE_API_KEY")
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
            except Exception as e:
                logger.error(f"Failed to add brave-search to DB: {e}")
                results["brave-search"] = "error"
        else:
            logger.debug("MCP 'brave-search' already in DB, skipping.")
            results["brave-search"] = "skipped"
    else:
        logger.debug("BRAVE_API_KEY not found. Skipping 'brave-search'.")
        results["brave-search"] = "skipped_no_key"

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


async def reload_mcp_for_workspace_change() -> dict[str, str]:
    """
    Reconfigure MCP servers when WORKSPACE_ROOT changes at runtime.

    This should be called after updating WORKSPACE_ROOT in SystemConfig.
    Only filesystem MCP needs to be reconfigured.

    Returns:
        Dict of server names and their status
    """
    logger.info("Reloading MCP configuration due to WORKSPACE_ROOT change...")
    results = {}

    # 1. Update DB config
    db_result = await init_mcp(force_update=True)
    results["db_update"] = db_result

    # 2. Disconnect and reconnect filesystem MCP
    try:
        from app.core.tools.mcp.client import mcp_client_manager

        # Disconnect existing if connected
        if "filesystem" in getattr(mcp_client_manager, 'sessions', {}):
            logger.info("Disconnecting existing filesystem MCP...")
            await mcp_client_manager.remove_server("filesystem")
            results["disconnect"] = "success"
        else:
            results["disconnect"] = "not_connected"

        # Reconnect (will load new config from DB)
        logger.info("Reconnecting filesystem MCP...")
        connected = await mcp_client_manager.ensure_connected("filesystem")
        results["reconnect"] = "success" if connected else "failed"

    except Exception as e:
        logger.error(f"Failed to reload MCP for workspace change: {e}")
        results["error"] = str(e)

    return results


def register_config_handlers():
    """Register configuration change handlers at startup."""
    async def _workspace_handler(old_value: str, new_value: str):
        """Handle WORKSPACE_ROOT changes."""
        logger.info(f"WORKSPACE_ROOT changed from '{old_value}' to '{new_value}'")
        result = await handle_config_change("WORKSPACE_ROOT", new_value)
        logger.info(f"Config change actions: {result}")

    SystemConfigService.register_change_handler("WORKSPACE_ROOT", _workspace_handler)
    logger.info("Registered WORKSPACE_ROOT change handler")


async def handle_config_change(key: str, new_value: str | None) -> dict[str, any]:
    """
    Handle system configuration changes at runtime.

    This function is called when a config value is updated via API.
    It performs necessary side effects (like restarting watchers, reconfiguring MCP, etc.)

    Args:
        key: The configuration key that changed
        new_value: The new value (or None if deleted)

    Returns:
        Dict with "success" (bool) and "actions" (list of performed actions)
    """
    actions = []

    if key == "WORKSPACE_ROOT":
        logger.info(f"WORKSPACE_ROOT changed to: {new_value}")

        # 1. Reconfigure filesystem MCP
        try:
            mcp_results = await reload_mcp_for_workspace_change()
            actions.append({"type": "mcp_reload", "results": mcp_results})
        except Exception as e:
            logger.error(f"Failed to reload MCP for workspace change: {e}")
            actions.append({"type": "mcp_reload", "error": str(e)})

        # 2. Update ThreadContextStore default root
        try:
            from app.core.context import thread_context_store
            if new_value:
                thread_context_store._default_root = os.path.abspath(new_value)
                actions.append({"type": "context_store_updated", "path": new_value})
        except Exception as e:
            logger.error(f"Failed to update ThreadContextStore: {e}")
            actions.append({"type": "context_store_update_failed", "error": str(e)})

        # 3. Trigger project reconciliation on new path
        if new_value and os.path.exists(new_value):
            try:
                from app.domain.project.sync_service import project_sync_service
                await project_sync_service.reconcile_projects(new_value)
                actions.append({"type": "project_reconcile", "path": new_value})
            except Exception as e:
                logger.error(f"Failed to reconcile projects: {e}")
                actions.append({"type": "project_reconcile_failed", "error": str(e)})

        # 4. Restart project discovery watcher
        try:
            from app.domain.watchers import ProjectDiscoveryWatcher
            # Note: This requires access to the running watcher instance
            # For now, we just log that a restart is needed
            logger.info("Project discovery watcher restart required for new WORKSPACE_ROOT")
            actions.append({"type": "watcher_restart_required"})
        except Exception as e:
            logger.error(f"Failed to handle watcher restart: {e}")

    elif key.startswith("EMBEDDING_"):
        logger.info(f"Embedding configuration changed: {key}")
        actions.append({"type": "config_updated", "note": "Embedding changes take effect on next indexing"})

    elif key.startswith("LLM_"):
        logger.info(f"LLM configuration changed: {key}")
        actions.append({"type": "config_updated", "note": "LLM changes take effect immediately"})

    else:
        actions.append({"type": "config_updated"})

    return {"success": True, "actions": actions}


def main() -> None:
    logger.info("Creating initial data")
    init()

    # Run Async Init for MCP and Atlas
    async def async_init():
        await init_atlas_config()
        await init_mcp()

    try:
        asyncio.run(async_init())
    except Exception as e:
        logger.error(f"Async initialization failed: {e}")

    logger.info("Initial data created")


if __name__ == "__main__":
    main()
