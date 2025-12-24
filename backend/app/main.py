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

# EvoLoop Imports
from app.core.workflows.workflow import create_graph
from app.core.globals import set_graph
from app.core.persistence import set_db_pool, set_checkpointer
from app.domain.project.summarizer import project_summarizer
from app.domain.codebase.indexing.manager import indexing_manager
from app.domain.project.service import project_context_manager
from app.domain.watchers import ProjectDiscoveryWatcher
from app.infrastructure.mcp.client import mcp_client_manager
from app.infrastructure.evoloop_link.client import init_evoloop_client
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

    # 2. Persistence (Checkpointer)
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
        
        root_projects_dir = settings.PROJECTS_ROOT
        if os.path.exists(root_projects_dir):
            discovery_watcher = ProjectDiscoveryWatcher(root_projects_dir)
            discovery_watcher.start()
        
        if default_path and os.path.exists(default_path):
            from app.domain.codebase.indexing.service import IndexingService
            service = IndexingService()
            repo_name = os.path.basename(default_path)
            repo = await service.get_or_create_repo(default_path, repo_name)
            await indexing_manager.start_watching(default_path, repo.id)
    except Exception as e:
        logger.error(f"Failed to start startup watcher: {e}")

    # 7. EvoLoop Link Client (PC Client)
    evoloop_client = None
    
    # Try to load token from settings OR local storage via infrastructure/external/imagicbox.py style
    # Actually, evoloop_link/client.py is separate.
    # Let's see if we can unify.
    
    evoloop_token = settings.EVOLOOP_LINK_TOKEN
    
    if not evoloop_token:
        # Check if we have a saved persisted token in Redis
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
            evoloop_client = init_evoloop_client(
                token=evoloop_token,
                device_name=settings.EVOLOOP_DEVICE_NAME
            )
            
            # USE GLOBALS TO SET CLIENT
            from app.infrastructure.evoloop_link.client import set_evoloop_client
            set_evoloop_client(evoloop_client)
            
            # Use shared handler
            from app.infrastructure.evoloop_link.handler import handle_remote_command, handle_project_switch_event
            
            evoloop_client.set_command_handler(handle_remote_command)
            
            # wrapper for event handling
            async def event_router(etype, edata):
                if etype == "project_switch":
                    await handle_project_switch_event(edata)
            
            evoloop_client.set_event_handler(event_router)

            # Override URLs if provided in settings
            if settings.EVOLOOP_LINK_BASE_URL:
                evoloop_client.base_url = settings.EVOLOOP_LINK_BASE_URL.rstrip("/")
            if settings.EVOLOOP_LINK_WS_URL:
                evoloop_client.ws_url = settings.EVOLOOP_LINK_WS_URL
            
            # Start client in background
            asyncio.create_task(evoloop_client.start())
            logger.info("EvoLoop Link Client started in background.")
        except Exception as e:
            logger.error(f"Failed to start EvoLoop Link Client: {e}")

    yield

    # --- Shutdown ---
    logger.info("Shutting down EvoLoop resources...")
    if discovery_watcher:
        discovery_watcher.stop()
    await indexing_manager.stop_all()
    await mcp_client_manager.cleanup()
    if evoloop_client:
        evoloop_client.stop()
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
