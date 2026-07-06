import logging
import os
import time
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings
from app.core.context.middleware import ContextMiddleware
from app.infrastructure.database.resource_manager import db_resource_manager

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

    await db_resource_manager.initialize(create_tables=True, seed_data=True)

    # Channel Registry - register built-in transports (SSE + Mobile)
    try:
        from app.core.channel import register_default_channels
        register_default_channels()
        logger.info("Channel registry initialized (SSE + Mobile).")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to initialize Channel registry: {e}")

    # Godcmd - register built-in admin commands
    try:
        from app.core.godcmd import register_builtin_commands
        register_builtin_commands()
        logger.info("Godcmd admin commands registered.")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to initialize Godcmd: {e}")

    # Memory System Init
    try:
        from app.core.memory.lifespan import MemoryLifespanManager
        memory_container = await MemoryLifespanManager.ainitialize()
        _app.state.memory_container = memory_container
        logger.info("Memory Service initialized via MemoryLifespanManager.")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to initialize Memory Service: {e}")

    # Agent Awakening - Discovery & Lifecycle Handlers
    try:
        from app.core.events.discovery import auto_discover_handlers
        auto_discover_handlers()
        logger.info("Discovery and registration of all domain lifecycle handlers complete.")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Agent Awakening/Discovery failed (non-critical): {e}")

    # Publish Application Started Event
    from app.core.events.publishers import publish_app_started
    await publish_app_started(startup_time)
    logger.info("[Startup] APP_STARTED event published")

    yield

    # --- Shutdown ---
    logger.info("Shutting down EvoLoop resources...")

    # 1. Publish Application Stopping Event
    # This triggers all decentalized LifecycleHandlers (EvoCloud, Memory, Indexing, MCP, etc.)
    try:
        from app.core.events.publishers import publish_app_stopping
        await publish_app_stopping()
        logger.info("[Shutdown] APP_STOPPING event published")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"[Shutdown] Failed to publish APP_STOPPING event: {e}")

    # 2. Cleanup Core Infrastructure (Infrastructure MUST be last)
    from app.infrastructure.llm.factory import shutdown_http_pool
    await shutdown_http_pool()
    await db_resource_manager.shutdown()

    logger.info("EvoLoop shutdown complete.")


def custom_generate_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.SERVICE_NAME,
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
