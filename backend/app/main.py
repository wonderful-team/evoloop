import logging
import os
import time
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.main import api_router
from app.core.config import settings
from app.core.context.middleware import ContextMiddleware
from app.core.routing.deps import is_loopback_host
from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.execution.macro import (
    migrate_deterministic_skills,
)

logging.basicConfig(level=settings.LOG_LEVEL)
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Global app reference for lifespan access
_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _app
    _app = app

    # Voice channel requires loopback binding (defence in depth lives in deps.py).
    _host = os.getenv("HOST", "127.0.0.1")
    if not is_loopback_host(_host):
        raise RuntimeError(
            f"Voice channel requires loopback binding; got HOST={_host}. "
            "Run with HOST=127.0.0.1 (e.g. HOST=127.0.0.1 bin/evo dev)."
        )

    # --- Startup ---
    startup_time = time.time()
    logger.info("Initializing EvoLoop resources...")

    await db_resource_manager.initialize(create_tables=True)

    # Restore persisted SharedState (active project_id) so voice / duty chains
    # get the correct project context even after a backend restart.
    try:
        from app.core.state import shared_state

        await shared_state.reload_persisted()
    except Exception as e:
        logger.warning(f"Failed to reload SharedState persisted project: {e}", exc_info=True)

    # Channel Registry - register built-in transports (SSE + Mobile)
    try:
        from app.core.channel import register_default_channels

        register_default_channels()
        logger.info("Channel registry initialized (SSE + Mobile).")
    except Exception as e:
        logger.warning(f"Failed to initialize Channel registry: {e}", exc_info=True)

    # Memory System Init
    try:
        from app.core.memory.lifespan import MemoryLifespanManager

        memory_container = await MemoryLifespanManager.ainitialize()
        _app.state.memory_container = memory_container
        logger.info("Memory Service initialized via MemoryLifespanManager.")
    except Exception as e:
        logger.warning(f"Failed to initialize Memory Service: {e}", exc_info=True)

    # Agent Awakening - Discovery & Lifecycle Handlers
    try:
        from app.core.events.discovery import auto_discover_handlers

        auto_discover_handlers()
        logger.info("Discovery and registration of all domain lifecycle handlers complete.")
    except Exception as e:
        logger.warning(f"Agent Awakening/Discovery failed (non-critical): {e}", exc_info=True)

    # Publish Application Started Event
    from app.core.events.publishers import publish_app_started

    await publish_app_started(startup_time)
    logger.info("[Startup] APP_STARTED event published")

    # L0 Matcher: dispatch Init Spec build (clients pull via GET /route/init).
    # The Huey worker writes the enriched RouteCatalog to the shared cache;
    # the API-side L0 matcher is lazily loaded from the same cache on the first
    # route request, so we do not rebuild it synchronously here.
    try:
        from app.core.routing import tasks as routing_tasks

        routing_tasks.build_l0_init_spec.delay()
        logger.info("[Startup] L0 Init Spec build dispatched")
    except Exception as e:
        logger.warning(f"[Startup] L0 Init Spec dispatch failed (non-critical): {e}", exc_info=True)

    # Wire voice WebSocket transport at startup so VoiceChannel (Agent TTS
    # streaming and macro presenters) can push to WS regardless of which code
    # path triggered the Agent — not just the first voice.route.
    try:
        from app.api.routes.voice_ws import _envelope as _ws_envelope
        from app.core.channel.output.voice_channel import VoiceChannel
        from app.core.schemas.canonical import MessageType as _MsgType
        from app.core.voice.connection import manager as _ws_manager

        VoiceChannel.bind(
            manager=_ws_manager,
            envelope_fn=_ws_envelope,
            message_type=_MsgType,
        )
        logger.info("[Startup] VoiceChannel WS transport wired")
    except (ImportError, TypeError) as e:
        logger.warning(
            "[Startup] VoiceChannel wiring failed (non-critical): %s", e, exc_info=True
        )

    # Migrate legacy deterministic LearnedSkill rows -> macros table (idempotent).
    # Runs after DB init so the macros table exists. Non-fatal: migration errors
    # are logged but do not prevent the server from starting.
    try:

        stats = await migrate_deterministic_skills()
        logger.info(
            "[Startup] Macro migration complete: migrated=%d skipped=%d failed=%d",
            stats.get("migrated", 0),
            stats.get("skipped", 0),
            stats.get("failed", 0),
        )
    except Exception as e:
        logger.warning(f"[Startup] Macro migration failed (non-critical): {e}", exc_info=True)

    yield

    # --- Shutdown ---
    logger.info("Shutting down EvoLoop resources...")

    # 1. Publish Application Stopping Event
    # This triggers all decentalized LifecycleHandlers (EvoCloud, Memory, Indexing, MCP, etc.)
    try:
        from app.core.events.publishers import publish_app_stopping

        await publish_app_stopping()
        logger.info("[Shutdown] APP_STOPPING event published")
    except Exception as e:
        logger.exception(f"[Shutdown] Failed to publish APP_STOPPING event: {e}")

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

register_exception_handlers(app)

# Mount static files
os.makedirs(settings.BROWSER_ARTIFACTS_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.BROWSER_ARTIFACTS_DIR), name="static")
