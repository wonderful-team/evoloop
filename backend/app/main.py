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
from app.core.context.middleware import ContextMiddleware

# Checkpointer imports - PostgreSQL for full mode, SQLite for embedded mode
if settings.EMBEDDED_MODE:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as Checkpointer
else:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver as Checkpointer
    from psycopg_pool import AsyncConnectionPool

# EvoLoop Imports
from app.core.context import thread_context_store
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.persistence import set_checkpointer, set_db_pool
from app.infrastructure.database.sql.database import Base, engine
from app.initial_data import init as init_data
from sqlmodel import SQLModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global app reference for lifespan access
_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _app
    _app = app

    # --- Startup ---
    startup_time = time.time()
    logger.info("Initializing EvoLoop resources...")

    # 1. DB Init
    if settings.EMBEDDED_MODE:
        logger.info("[lifespan] Embedded mode detected. Creating SQLite tables...")
        from app import models  # noqa: F401
        from app.domain.project.requirements import models as _req_models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("[lifespan] SQLite tables created successfully")
    else:
        logger.info("[lifespan] Full mode detected. Initializing PostgreSQL...")
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("[lifespan] PostgreSQL initialized")

    # 1.5 Seed Initial Data (System Config)
    await asyncio.to_thread(init_data)

    # 2. Memory System Init
    try:
        from app.core.memory.lifespan import MemoryLifespanManager
        memory_container = await MemoryLifespanManager.ainitialize()
        _app.state.memory_container = memory_container
        logger.info("Memory Service initialized via MemoryLifespanManager.")
    except Exception as e:
        logger.warning(f"Failed to initialize Memory Service: {e}")

    # 2.5 Agent Awakening - Discovery & Lifecycle Handlers
    try:
        from app.core.events.discovery import auto_discover_handlers
        auto_discover_handlers()
        logger.info("Discovery and registration of all domain lifecycle handlers complete.")
    except Exception as e:
        logger.warning(f"Agent Awakening/Discovery failed (non-critical): {e}")

    # 3. Persistence (Checkpointer)
    db_uri = settings.CHECKPOINTER_DATABASE_URI
    db_pool = None
    _sqlite_conn = None

    if settings.EMBEDDED_MODE:
        import aiosqlite
        sqlite_path = db_uri.replace("sqlite+aiosqlite:///", "").replace("sqlite://", "")
        _sqlite_conn = await aiosqlite.connect(sqlite_path)
        checkpointer = Checkpointer(conn=_sqlite_conn)
        await checkpointer.setup()
        logger.info("[lifespan] SQLite checkpointer initialized")
    else:
        db_pool = AsyncConnectionPool(conninfo=db_uri, max_size=20, kwargs={"autocommit": True}, open=False)
        await db_pool.open()
        checkpointer = Checkpointer(db_pool)
        await checkpointer.setup()
        set_db_pool(cast(Any, db_pool))

    set_checkpointer(checkpointer)

    # 4. Engine Graph (Dynamic Build)
    try:
        builder = GraphBuilder()
        config_path = os.path.join(os.path.dirname(__file__), "core/engine/config/agent_main.yaml")
        graph = builder.build(config_path, checkpointer=checkpointer)
        set_graph(graph, config_path=config_path, checkpointer=checkpointer)
        logger.info(f"Agent Graph built successfully from {config_path}")
    except Exception as e:
        logger.critical(f"Failed to build Agent Graph: {e}")
        raise

    # 5. Domain Cleanup/Setup - Now managed by LifecycleHandlers
    # (EvoCloud bridge, Discovery, Indexing, MCP, Knowledge Base)

    # 11. Publish Application Started Event
    from app.core.events import system_bus, SystemEventType, BaseEvent
    await system_bus.publish(BaseEvent(
        event_type=SystemEventType.APP_STARTED,
        source="main",
        data={"startup_time": startup_time}
    ))
    logger.info("[Startup] APP_STARTED event published")

    yield

    # --- Shutdown ---
    logger.info("Shutting down EvoLoop resources...")
    
    # 1. Publish Application Stopping Event
    # This triggers all decentalized LifecycleHandlers (EvoCloud, Memory, Indexing, MCP, etc.)
    try:
        from app.core.events import system_bus, SystemEventType, BaseEvent
        await system_bus.publish(BaseEvent(
            event_type=SystemEventType.APP_STOPPING,
            source="main",
            data={}
        ))
        logger.info("[Shutdown] APP_STOPPING event published")
    except Exception as e:
        logger.error(f"[Shutdown] Failed to publish APP_STOPPING event: {e}")
    
    # 2. Cleanup Core Infrastructure (Infrastructure MUST be last)
    # Close database connections (Checkpointer & Main DB)
    if db_pool:
        await db_pool.close()
    if _sqlite_conn:
        await _sqlite_conn.close()
        logger.info("SQLite checkpointer connection closed")

    logger.info("EvoLoop shutdown complete.")


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
os.makedirs(settings.BROWSER_ARTIFACTS_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.BROWSER_ARTIFACTS_DIR), name="static")
