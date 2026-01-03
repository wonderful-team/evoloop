import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import os
import asyncio

from app.api.main import api_router
from app.core.config import settings
from app.logging import logger
from fastapi.staticfiles import StaticFiles

# EvoLoop Imports
from app.core.workflows.workflow import create_graph
from app.core.globals import set_graph
from app.core.persistence import set_db_pool, set_checkpointer
from app.domain.project.summarizer import project_summarizer
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.project.service import project_context_manager
from app.domain.watchers import ProjectDiscoveryWatcher
from app.infrastructure.mcp.client import mcp_client_manager

from app.infrastructure.database.sql.database import engine, Base
from sqlalchemy import text

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Initializing EvoLoop resources...")
    
    # 1. DB Init
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        
    # 2. Graph/Memory Init
    try:
        from app.domain.memory.service import memory_service
        await memory_service.initialize_schema()
        logger.info("Memory Service schema initialized.")
    except Exception as e:
        logger.warning(f"Failed to initialize Memory Service schema: {e}")
        
    # 3. Persistence (Checkpointer)
    db_uri = settings.CHECKPOINTER_DATABASE_URI
    # kwargs={"autocommit": True} is required for CREATE INDEX CONCURRENTLY in setup()
    db_pool = AsyncConnectionPool(conninfo=db_uri, max_size=20, kwargs={"autocommit": True}, open=False)
    await db_pool.open()
    checkpointer = AsyncPostgresSaver(db_pool)
    await checkpointer.setup()
    
    # Set globals
    set_db_pool(db_pool)
    set_checkpointer(checkpointer)
    
    # 3. Graph
    graph = create_graph(checkpointer=checkpointer)
    set_graph(graph)
        
    # 4. Project Summarizer
    await project_summarizer.start_worker()

    # 5. MCP Clients
    try:
        await mcp_client_manager.connect_all()
    except Exception as e:
        logger.error(f"Failed to connect to MCP servers: {e}")

    # 6. Watchers
    discovery_watcher = None
    try:
        default_path = project_context_manager.get_working_directory("default")
        
        # Validate default_path: It should NOT be the PROJECTS_ROOT itself.
        # If get_working_directory returns the root dir, it means no specific project is selected.
        # We should skip indexing in that case to avoid indexing ALL projects as one big repo.
        root_projects_dir = settings.PROJECTS_ROOT
        
        is_root_dir = False
        if default_path and root_projects_dir:
             if os.path.abspath(default_path) == os.path.abspath(root_projects_dir):
                 is_root_dir = True

        if os.path.exists(root_projects_dir):
            discovery_watcher = ProjectDiscoveryWatcher(root_projects_dir)
            discovery_watcher.start()
        
        if default_path and os.path.exists(default_path) and not is_root_dir:
            from app.domain.codebase.indexing.service import IndexingService
            service = IndexingService()
            repo_name = os.path.basename(default_path)
            repo = await service.get_or_create_repo(default_path, repo_name)
            await indexing_manager.start_watching(default_path, repo.id)
            
            # Start full indexing for the default/startup project
            # This ensures we catch up if the server was down.
            indexing_manager.run_indexing_background(repo.id)

    except Exception as e:
        logger.error(f"Failed to start startup watcher: {e}")

    # 7. EvoLoop Link Client (Unified)
    # Restore session if token exists
    
    # Imports
    from app.infrastructure.external.imagicbox import imagicbox_client
    from app.infrastructure.evoloop_link.handler import handle_remote_command, handle_project_switch_event
    
    # Config Handlers
    imagicbox_client.set_command_handler(handle_remote_command)
    
    async def event_router(etype, edata):
        if etype == "project_switch":
            await handle_project_switch_event(edata)
    imagicbox_client.set_event_handler(event_router)

    # Try to load token from Redis to auto-connect
    evoloop_token = settings.IMAGICBOX_ACCESS_TOKEN # Check config first
    
    if not evoloop_token:
        try:
            import redis.asyncio as redis
            redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            async with redis_client:
                evoloop_token = await redis_client.get("evoloop:link:token")
                if evoloop_token:
                     logger.info("[EvoLoop] Found persisted token in Redis, auto-connecting...")
        except Exception as e:
            logger.warning(f"[EvoLoop] Failed to read token from Redis: {e}")

    if evoloop_token:
        try:
             # This will set the token on client and start the loop
             await imagicbox_client.start_device_link(token=evoloop_token)
             logger.info("EvoLoop Link Client started in background.")

             # Fetch Current Project from Member Center
             try:
                 # Give it a small delay? No, http request is independent of WS.
                 res = await imagicbox_client.get_current_project()
                 if res.get("code") == 0:
                     project_data = res.get("data", {})
                     cloud_path = project_data.get("external_path")
                     if cloud_path and os.path.exists(cloud_path):
                         logger.info(f"[Startup] Synced active project from Cloud: {cloud_path}")
                         # Update context immediately for default thread
                         project_context_manager.set_working_directory("default", cloud_path)
                         
                         # Trigger indexing for this scoped project immediately?
                         # The watcher block above (step 6) might have already run with default?
                         # Actually, step 6 runs BEFORE step 7 in current file structure?
                         # Wait, I see step 6 is before step 7 in line 72 vs 105.
                         # This means watchers start with potentially STALE default, then we fetch cloud.
                         # We should RE-TRIGGER watcher if cloud differs.
                         
                         from app.domain.codebase.indexing.service import IndexingService
                         service = IndexingService()
                         repo_name = os.path.basename(cloud_path)
                         repo = await service.get_or_create_repo(cloud_path, repo_name)
                         await indexing_manager.start_watching(cloud_path, repo.id)
                         indexing_manager.run_indexing_background(repo.id)
                         
                     else:
                         logger.info(f"[Startup] Cloud active project path invalid or local missing: {cloud_path}")
                 else:
                     logger.warning(f"[Startup] Failed to fetch current project: {res.get('message')}")
             except Exception as proj_e:
                 logger.warning(f"[Startup] Error syncing project: {proj_e}")

        except Exception as e:
            logger.error(f"Failed to start EvoLoop Link Client: {e}")

    yield

    # --- Shutdown ---
    logger.info("Shutting down EvoLoop resources...")
    if discovery_watcher:
        discovery_watcher.stop()
    await indexing_manager.stop_all()
    await mcp_client_manager.cleanup()
    
    # Stop EvoLoop Link
    try:
        from app.infrastructure.external.imagicbox import imagicbox_client
        await imagicbox_client.stop_device_link()
    except Exception as e:
        logger.warning(f"Failed to stop EvoLoop Link: {e}")
        
    if db_pool:
        await db_pool.close()


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan
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

app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount static files
browser_artifacts_dir = os.path.join(os.getcwd(), "browser_artifacts")
os.makedirs(browser_artifacts_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=browser_artifacts_dir), name="static")
