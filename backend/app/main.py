import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, cast

import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings

# Checkpointer imports - PostgreSQL for full mode, SQLite for embedded mode
if settings.EMBEDDED_MODE:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as Checkpointer
else:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver as Checkpointer
    from psycopg_pool import AsyncConnectionPool

# EvoLoop Imports
from app.core.context import thread_context_store
from app.core.context.middleware import ContextMiddleware
from app.core.engine.graph_builder import GraphBuilder
from app.core.events.bridge import register_event_bridge
from app.core.evocloud import evocloud_manager
from app.core.globals import set_graph
from app.core.persistence import set_checkpointer, set_db_pool
from app.core.tools.mcp.client import mcp_client_manager
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.project.discovery_manager import discovery_manager
from app.domain.project.summarizer import project_summarizer
from app.core.learning.discovery import skill_discovery
from app.infrastructure.config import SystemConfigService
from app.infrastructure.database.sql.database import Base, engine
from app.initial_data import init as init_data, register_config_handlers, init_atlas_config, init_mcp
from sqlmodel import SQLModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _warm_evocloud_cache():
    """Background task to warm EvoCloud projects cache."""
    try:
        from app.core.evocloud import evocloud_manager
        projects = await evocloud_manager.scan_projects()
        logger.info(f"[Startup] ✓ EvoCloud projects cache warmed: {len(projects)} projects")
    except Exception as e:
        logger.warning(f"[Startup] EvoCloud cache warming failed: {e}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # --- Startup ---
    logger.info("Initializing EvoLoop resources...")

    # 1. DB Init
    if settings.EMBEDDED_MODE:
        # Embedded Mode (SQLite): Auto-create all tables
        logger.info("[lifespan] Embedded mode detected. Creating SQLite tables...")
        # Import all models to ensure they're registered with SQLModel metadata
        from app import models  # noqa: F401
        # Also import SQLAlchemy ORM models (requirements models use Base, not SQLModel)
        from app.domain.project.requirements import models as _req_models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("[lifespan] SQLite tables created successfully")
    else:
        # Full Mode (PostgreSQL): Create extension and tables
        logger.info("[lifespan] Full mode detected. Initializing PostgreSQL...")
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("[lifespan] PostgreSQL initialized")

    # 1.5 Seed Initial Data (System Config)
    # This runs sychronously, so we offload to thread
    await asyncio.to_thread(init_data)

    # 1.6 Register Config Change Handlers
    # This must happen after init_data() so SystemConfigService is ready
    try:
        register_config_handlers()
        logger.info("Configuration change handlers registered.")
    except Exception as e:
        logger.warning(f"Failed to register config handlers: {e}")

    # 2. Graph/Memory Init
    try:
        from app.core.memory import memory_manager

        await memory_manager.initialize()
        logger.info("Memory Service schema initialized.")
    except Exception as e:
        logger.warning(f"Failed to initialize Memory Service schema: {e}")

    # 2.5 Agent Awakening - Environment & Capability Awareness
    try:
        from app.core.environment import awaken, environment_watcher
        from app.core.environment.handlers import register_default_handlers
        from app.domain.codebase.indexing.event_handlers import register_indexing_handlers
        from app.core.learning.orchestrator import register_learning_handlers

        # Register event handlers before awakening
        register_default_handlers()
        register_indexing_handlers()
        register_event_bridge()
        register_learning_handlers()

        await awaken()
        logger.info("Agent Awakening complete.")

        # Start background environment watcher
        await environment_watcher.start()

        # 2.6 Atlas Configuration Initialization
        try:
            await init_atlas_config()
            logger.info("Atlas configuration initialized.")
        except Exception as e:
            logger.warning(f"Atlas config initialization failed (non-critical): {e}")

        # 2.7 MCP Server Configuration
        # Must run after SystemConfig is seeded (for WORKSPACE_ROOT)
        # This adds MCP configs to DB; actual connection happens in connect_all()
        try:
            mcp_results = await init_mcp()
            logger.info(f"MCP servers added to DB: {mcp_results}")
        except Exception as e:
            logger.warning(f"MCP configuration failed (non-critical): {e}")

        # 2.8 Skill Discovery Sync & Warm-up
        try:
            await skill_discovery._sync_system_skills()
            await skill_discovery.get_active_skills_list() # Warm up O(1) Memory Index
            logger.info("Skill synchronization and warm-up complete.")
        except Exception as e:
            logger.warning(f"Skill synchronization failed (non-critical): {e}")

    except Exception as e:
        logger.warning(f"Agent Awakening failed (non-critical): {e}")

    # 3. Persistence (Checkpointer)
    db_uri = settings.CHECKPOINTER_DATABASE_URI
    db_pool = None  # Initialize for cleanup in shutdown
    _sqlite_conn = None  # Keep reference for cleanup

    if settings.EMBEDDED_MODE:
        # Embedded Mode: Use AsyncSqliteSaver (no connection pool needed)
        logger.info("[lifespan] Initializing SQLite checkpointer for embedded mode...")
        import aiosqlite
        # Extract path from sqlite+aiosqlite:///path
        sqlite_path = db_uri.replace("sqlite+aiosqlite:///", "").replace("sqlite://", "")
        _sqlite_conn = await aiosqlite.connect(sqlite_path)
        checkpointer = Checkpointer(conn=_sqlite_conn)
        await checkpointer.setup()
        logger.info("[lifespan] SQLite checkpointer initialized")
    else:
        # Full Mode: Use PostgreSQL connection pool
        # kwargs={"autocommit": True} is required for CREATE INDEX CONCURRENTLY in setup()
        db_pool = AsyncConnectionPool(conninfo=db_uri, max_size=20, kwargs={"autocommit": True}, open=False)
        await db_pool.open()
        checkpointer = Checkpointer(db_pool)
        await checkpointer.setup()

        # Set globals (PostgreSQL pool for cleanup)
        set_db_pool(cast(Any, db_pool))

    set_checkpointer(checkpointer)

    # 3. Graph (Dynamic Build)
    try:
        builder = GraphBuilder()
        # Path to the primary config
        config_path = os.path.join(os.path.dirname(__file__), "core/engine/config/agent_main.yaml")
        graph = builder.build(config_path, checkpointer=checkpointer)
        set_graph(graph, config_path=config_path, checkpointer=checkpointer)
        logger.info(f"Agent Graph built successfully from {config_path}")
    except Exception as e:
        logger.critical(f"Failed to build Agent Graph: {e}")
        raise

    # 4. Project Summarizer
    await project_summarizer.start_worker()

    # 5. MCP Clients
    try:
        await mcp_client_manager.connect_all()
    except Exception as e:
        logger.error(f"Failed to connect to MCP servers: {e}")

    # 6. Watchers
    logger.info("Initializing File Watchers...")
    try:
        default_path = thread_context_store.get_working_directory("default")

        # Validate default_path: It should NOT be the WORKSPACE_ROOT itself.
        # If get_working_directory returns the root dir, it means no specific project is selected.
        # We should skip indexing in that case to avoid indexing ALL projects as one big repo.
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

            # 6.4 Start Project Discovery Manager
            discovery_manager.start(root_projects_dir)

            # 6.5 Startup Reconciliation
            # Catch up on offline changes (creates, deletes)
            try:
                from app.domain.project.sync_service import project_sync_service

                # Run reconciliation in background to not block startup significantly,
                # or await it if critical? Await is safer to ensure state consistency before accepting requests.
                # However, for large folders, it might be slow.
                # But let's await it for V1 safety.
                logger.debug(f"DEBUG: Triggering reconcile_projects on {root_projects_dir}")
                await project_sync_service.reconcile_projects(root_projects_dir)
            except Exception as e:
                logger.error(f"Startup Reconciliation failed: {e}")
                logger.debug(f"DEBUG: Startup Reconciliation failed: {e}")

        if default_path and os.path.exists(default_path) and not is_root_dir:
            from app.domain.codebase.indexing.service import IndexingService

            service = IndexingService()
            repo_name = os.path.basename(default_path)
            repo = await service.get_or_create_repo(default_path, repo_name)
            await indexing_manager.start_watching(default_path, repo.id)

            # NOTE: Deep indexing is deferred until after user login
            # to avoid wasting resources on projects user may not care about.
            # File watching is active, so changes will be captured.
            # await indexing_manager.run_indexing_background(repo.id)

    except Exception as e:
        logger.error(f"Failed to start startup watcher: {e}")

    # 6.6 Register WORKSPACE_ROOT change handler
    async def on_workspace_root_changed(old_root: str, new_root: str):
        """Handle WORKSPACE_ROOT configuration change."""
        logger.info(f"[ConfigChange] WORKSPACE_ROOT changed from '{old_root}' to '{new_root}'")

        # Update ThreadContextStore default root
        thread_context_store._default_root = os.path.abspath(new_root)
        logger.info(f"[ConfigChange] Updated ThreadContextStore default root to: {new_root}")

        # Use discovery_manager to switch root (handles stop/start/reconcile)
        await discovery_manager.switch_root(new_root)

    # Register the handler
    SystemConfigService.register_change_handler("WORKSPACE_ROOT", on_workspace_root_changed)
    logger.info("[ConfigChange] Registered WORKSPACE_ROOT change handler")

    # 7. EvoLoop Link Client (Unified)
    from app.core.evocloud.bridge.handlers import handle_project_switch_event, handle_remote_command

    # Initialize Core Module
    evocloud_manager.initialize()

    # Config Handlers
    evocloud_manager.set_command_handler(handle_remote_command)

    async def event_router(etype, edata):
        if etype == "project_switch":
            await handle_project_switch_event(edata)

    # Fallback: Check if client has persisted token (auth.json)
    # The manager's API backend should have loaded it if implemented correctly.
    # Otherwise we try to load it or check if it's already set.
    evoloop_token = None
    if evocloud_manager.api:
        evoloop_token = evocloud_manager.api.get_token()
        if evoloop_token:
            logger.info("[EvoLoop] Found persisted token in auth.json, auto-connecting...")

    if evoloop_token and evocloud_manager.link:
        try:
            # This will set the token on client and start the loop
            # Ensure link uses the same token (already set in api)
            await evocloud_manager.link.start()
            logger.info("EvoLoop Link Client started in background.")

            # Fetch Current Project from Member Center
            try:
                # Give it a small delay? No, http request is independent of WS.
                res = await evocloud_manager.api.get_current_project()
                if res.get("code") == 0:
                    project_data = res.get("data", {})
                    cloud_path = project_data.get("external_path")
                    if cloud_path and os.path.exists(cloud_path):
                        # Check if this project was locally ignored
                        from app.domain.project import cache as project_cache

                        is_ignored = await project_cache.is_path_ignored(cloud_path)
                        if not is_ignored:
                            # Also check DB directly as fallback
                            from app.domain.codebase.indexing.service import IndexingService

                            service = IndexingService()
                            existing_repo = await service.get_repo_by_path(cloud_path)
                            if existing_repo and existing_repo.sync_status == "IGNORED":
                                is_ignored = True
                                logger.info(f"[Startup] Project {cloud_path} is marked as IGNORED in DB. Skipping cloud sync.")

                        if is_ignored:
                            logger.info(f"[Startup] Skipping cloud project sync for ignored path: {cloud_path}")
                        else:
                            logger.info(f"[Startup] Synced active project from Cloud: {cloud_path}")
                            # Update context immediately for default thread
                            thread_context_store.set_working_directory("default", cloud_path)

                            project_id = project_data.get("project_id")

                            from app.domain.codebase.indexing.service import IndexingService

                            service = IndexingService()
                            repo_name = os.path.basename(cloud_path)
                            repo = await service.get_or_create_repo(cloud_path, repo_name, project_id=project_id)
                            await indexing_manager.start_watching(cloud_path, repo.id)
                            # NOTE: Deep indexing deferred to post-login to save resources
                            # await indexing_manager.run_indexing_background(repo.id)

                    else:
                        logger.info(f"[Startup] Cloud active project path invalid or local missing: {cloud_path}")
                else:
                    logger.warning(f"[Startup] Failed to fetch current project: {res.get('message')}")
            except Exception as proj_e:
                logger.warning(f"[Startup] Error syncing project: {proj_e}")

        except Exception as e:
            logger.error(f"Failed to start EvoLoop Link Client: {e}")

    # 8. Android Device Watcher
    try:
        from app.core.environment.controllers.device_watcher import device_watcher
        device_watcher.start()
    except Exception as e:
        logger.warning(f"Failed to start Device Watcher: {e}")

    # 9. Pre-Supervisor Optimizations - Cache Warming
    # Warm up caches that are safe to preload (no query-dependent data)
    try:
        logger.info("[Startup] Warming up caches for Pre-Supervisor optimization...")
        start_warm = time.time()
        
        # 9.1 Skill Discovery Cache - Preload all active skills
        try:
            from app.core.learning.discovery import skill_discovery
            skills = await skill_discovery.get_active_skills_list()
            logger.info(f"[Startup] ✓ Skills cache warmed: {len(skills)} skills")
        except Exception as e:
            logger.warning(f"[Startup] Failed to warm skills cache: {e}")
        
        # 9.2 System Config Cache - Preload language preference
        try:
            lang_pref = SystemConfigService.get_language_preference()
            logger.info(f"[Startup] ✓ User preferences cached: language={lang_pref}")
        except Exception as e:
            logger.warning(f"[Startup] Failed to cache user preferences: {e}")
        
        # 9.3 EvoCloud Projects Cache - Async background fetch
        try:
            if evocloud_manager.get_token():
                # Fire and forget - don't block startup
                asyncio.create_task(_warm_evocloud_cache())
        except Exception as e:
            logger.warning(f"[Startup] Failed to start EvoCloud cache warming: {e}")
        
        warm_time = (time.time() - start_warm) * 1000
        logger.info(f"[Startup] Cache warming completed in {warm_time:.1f}ms")
        
    except Exception as e:
        logger.warning(f"[Startup] Cache warming failed: {e}")

    yield

    # --- Shutdown ---
    logger.info("Shutting down EvoLoop resources...")
    # Stop discovery manager
    try:
        discovery_manager.stop()
    except Exception as e:
        logger.warning(f"Failed to stop discovery manager: {e}")
    await indexing_manager.stop_all()
    await mcp_client_manager.cleanup()

    # Stop Mirror Sessions
    try:
        from app.core.environment.controllers.mirror_session import mirror_manager
        mirror_manager.cleanup()
    except Exception as e:
        logger.warning(f"Failed to cleanup mirror sessions: {e}")

    # Stop Environment Watcher
    try:
        from app.core.environment import environment_watcher
        await environment_watcher.stop()
    except Exception as e:
        logger.warning(f"Failed to stop Environment Watcher: {e}")

    # Stop Device Watcher
    try:
        from app.core.environment.controllers.device_watcher import device_watcher
        device_watcher.stop()
    except Exception as e:
        logger.warning(f"Failed to stop Device Watcher: {e}")

    # Stop EvoLoop Link
    try:
        if evocloud_manager.link:
            await evocloud_manager.link.stop()
    except Exception as e:
        logger.warning(f"Failed to stop EvoLoop Link: {e}")

    # Close database connections
    if db_pool:
        await db_pool.close()
    if _sqlite_conn:
        await _sqlite_conn.close()
        logger.info("SQLite checkpointer connection closed")


def custom_generate_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(ContextMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount static files
# Mount static files
os.makedirs(settings.BROWSER_ARTIFACTS_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.BROWSER_ARTIFACTS_DIR), name="static")
