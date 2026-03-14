import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import Any, cast

from app.core.config import settings

# EvoLoop Imports
from app.core.context import thread_context_store
from app.core.events.bridge import register_event_bridge
from app.core.evocloud import evocloud_manager
from app.core.tools.mcp.client import mcp_client_manager
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.project.discovery_manager import discovery_manager
from app.domain.project.summarizer import project_summarizer
from app.infrastructure.config import SystemConfigService
from app.infrastructure.database.sql.database import Base, engine
from app.initial_data import init as init_data, register_config_handlers, init_atlas_config, init_mcp
from app.sidecar.handlers import register_all_handlers
from app.sidecar.handlers.events import setup_event_forwarding, events
from app.sidecar.protocol import get_protocol, SidecarProtocol

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class EvoLoopClient:
    """EvoLoop Client Application - Local Agent Daemon (Sidecar Mode)

    The client runs as a sidecar process, communicating with Tauri via stdin/stdout.
    No HTTP API, no WebSocket - pure JSON Lines protocol.
    """

    def __init__(self):
        self.db_pool = None
        self.checkpointer = None
        self.graph = None
        self._shutdown_event = asyncio.Event()
        self._protocol: SidecarProtocol = get_protocol()

    async def start(self):
        """Start the EvoLoop client daemon."""
        logger.info("=" * 60)
        logger.info("Starting EvoLoop Client Daemon (Sidecar Mode)")
        logger.info("=" * 60)

        await self._initialize()

        # Register signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        # Start the Sidecar protocol loop (blocking)
        logger.info("Starting Sidecar protocol loop...")
        try:
            await self._protocol.start()
        except Exception as e:
            logger.error(f"Protocol loop error: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """Stop the client daemon."""
        if not self._shutdown_event.is_set():
            logger.info("Shutdown signal received...")
            self._shutdown_event.set()
            await self._protocol.stop()

    async def _initialize(self):
        """Initialize all client components."""
        # 1. DB Init - Import all models first so they're registered with metadata
        from app.models import SQLModel  # noqa: F401 - imports all models via __init__
        from sqlalchemy import text

        async with engine.begin() as conn:
            # Use SQLModel.metadata to include all SQLModel-based tables
            await conn.run_sync(SQLModel.metadata.create_all)
            # Also create SQLAlchemy-based model tables (Atlas, Codebase, etc.)
            await conn.run_sync(Base.metadata.create_all)

        # 1.5 Seed Initial Data (System Config)
        await asyncio.to_thread(init_data)

        # 1.6 Register Config Change Handlers
        try:
            register_config_handlers()
            logger.info("Configuration change handlers registered.")
        except Exception as e:
            logger.warning(f"Failed to register config handlers: {e}")

        # 2. Register Sidecar protocol handlers
        register_all_handlers(self._protocol)
        setup_event_forwarding()
        logger.info("Sidecar protocol handlers registered.")

        # 3. Graph/Memory Init
        try:
            from app.core.memory import memory_manager
            await memory_manager.initialize()
            logger.info("Memory Service schema initialized.")
        except Exception as e:
            logger.warning(f"Failed to initialize Memory Service schema: {e}")

        # 4. Agent Awakening - Environment & Capability Awareness
        try:
            from app.core.environment import awaken, environment_watcher
            from app.core.environment.handlers import register_default_handlers
            from app.domain.codebase.indexing.event_handlers import register_indexing_handlers

            register_default_handlers()
            register_indexing_handlers()
            register_event_bridge()

            await awaken()
            logger.info("Agent Awakening complete.")

            await environment_watcher.start()

            # 4.1 Atlas Configuration Initialization
            try:
                await init_atlas_config()
                logger.info("Atlas configuration initialized.")
            except Exception as e:
                logger.warning(f"Atlas config initialization failed (non-critical): {e}")

            # 4.2 MCP Server Configuration
            try:
                mcp_results = await init_mcp()
                logger.info(f"MCP servers added to DB: {mcp_results}")
            except Exception as e:
                logger.warning(f"MCP configuration failed (non-critical): {e}")

        except Exception as e:
            logger.warning(f"Agent Awakening failed (non-critical): {e}")

        # 5. Project Summarizer
        await project_summarizer.start_worker()

        # 6. MCP Clients
        try:
            await mcp_client_manager.connect_all()
            # Send event for each connected MCP server
            if hasattr(mcp_client_manager, 'sessions'):
                for server_name in mcp_client_manager.sessions:
                    await events.mcp_connected(server_name)
        except Exception as e:
            logger.error(f"Failed to connect to MCP servers: {e}")

        # 7. File Watchers
        logger.info("Initializing File Watchers...")
        try:
            default_path = thread_context_store.get_working_directory("default")
            db_workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
            root_projects_dir = db_workspace_root if db_workspace_root else settings.WORKSPACE_ROOT

            if not root_projects_dir:
                logger.warning("WORKSPACE_ROOT not configured. Skipping project discovery.")
            elif not os.path.exists(root_projects_dir):
                logger.warning(f"WORKSPACE_ROOT '{root_projects_dir}' does not exist. Skipping project discovery.")
            else:
                is_root_dir = False
                if default_path and root_projects_dir:
                    if os.path.abspath(default_path) == os.path.abspath(root_projects_dir):
                        is_root_dir = True

                discovery_manager.start(root_projects_dir)

                if default_path and os.path.exists(default_path) and not is_root_dir:
                    from app.domain.codebase.indexing.service import IndexingService

                    service = IndexingService()
                    repo_name = os.path.basename(default_path)
                    repo = await service.get_or_create_repo(default_path, repo_name)
                    await indexing_manager.start_watching(default_path, repo.id)

        except Exception as e:
            logger.error(f"Failed to start startup watcher: {e}")

        # 8. Android Device Watcher
        try:
            from app.core.environment.controllers.device_watcher import device_watcher
            device_watcher.start()
        except Exception as e:
            logger.warning(f"Failed to start Device Watcher: {e}")

        # 9. Send ready event to Tauri
        await events._send("ready", {
            "capabilities": [
                "file_read", "file_write", "file_list", "shell", "mcp", "get_context"
            ],
            "workspace_root": SystemConfigService.get_value("WORKSPACE_ROOT") or settings.WORKSPACE_ROOT,
        })

        logger.info("Client initialization complete, ready for commands.")

    async def cleanup(self):
        """Cleanup resources on shutdown."""
        logger.info("Shutting down EvoLoop resources...")

        # Notify Tauri we're shutting down
        try:
            await events._send("shutdown", {"reason": "cleanup"})
        except:
            pass

        try:
            discovery_manager.stop()
        except Exception as e:
            logger.warning(f"Failed to stop discovery manager: {e}")

        try:
            await indexing_manager.stop_all()
        except Exception as e:
            logger.warning(f"Failed to stop indexing manager: {e}")

        try:
            await mcp_client_manager.cleanup()
        except Exception as e:
            logger.warning(f"Failed to cleanup MCP clients: {e}")

        try:
            from app.core.environment.controllers.mirror_session import mirror_manager
            mirror_manager.cleanup()
        except Exception as e:
            logger.warning(f"Failed to cleanup mirror sessions: {e}")

        try:
            from app.core.environment import environment_watcher
            await environment_watcher.stop()
        except Exception as e:
            logger.warning(f"Failed to stop Environment Watcher: {e}")

        try:
            from app.core.environment.controllers.device_watcher import device_watcher
            device_watcher.stop()
        except Exception as e:
            logger.warning(f"Failed to stop Device Watcher: {e}")


# Global client instance
_client: EvoLoopClient | None = None


async def main():
    """Main entry point for EvoLoop Client."""
    global _client
    _client = EvoLoopClient()

    try:
        await _client.start()
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    finally:
        await _client.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
