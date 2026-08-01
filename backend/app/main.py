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
from app.core.routing.deps import is_loopback_host
from app.infrastructure.database.resource_manager import db_resource_manager

logging.basicConfig(level=logging.INFO)
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

    # Channel Registry - register built-in transports (SSE + Mobile)
    try:
        from app.core.channel import register_default_channels
        register_default_channels()
        logger.info("Channel registry initialized (SSE + Mobile).")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.warning(f"Failed to initialize Channel registry: {e}")

    # Memory System Init
    try:
        from app.core.memory.lifespan import MemoryLifespanManager
        memory_container = await MemoryLifespanManager.ainitialize()
        _app.state.memory_container = memory_container
        logger.info("Memory Service initialized via MemoryLifespanManager.")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.warning(f"Failed to initialize Memory Service: {e}")

    # Agent Awakening - Discovery & Lifecycle Handlers
    try:
        from app.core.events.discovery import auto_discover_handlers
        auto_discover_handlers()
        logger.info("Discovery and registration of all domain lifecycle handlers complete.")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.warning(f"Agent Awakening/Discovery failed (non-critical): {e}")

    # Publish Application Started Event
    from app.core.events.publishers import publish_app_started
    await publish_app_started(startup_time)
    logger.info("[Startup] APP_STARTED event published")

    # Voice assistant: dispatch Init Spec build (clients pull via GET /route/init).
    try:
        from app.core.routing import tasks as _voice_tasks
        _voice_tasks.build_voice_init_spec.delay()
        logger.info("[Startup] Voice Init Spec build dispatched")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.warning(f"[Startup] Voice Init Spec dispatch failed (non-critical): {e}")

    # Preheat L0 local matcher: build + enrich + compile regex so the first
    # voice.route does not pay the cold-start penalty (~1s).
    try:
        from app.core.routing.matcher_cache import matcher_cache
        await matcher_cache.rebuild()
        logger.info("[Startup] L0 local matcher preheated")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.warning(f"[Startup] L0 local matcher preheat failed (non-critical): {e}")

    # Wire voice executor globals at startup so VoiceChannel (Agent TTS
    # streaming) can push to WS regardless of which code path triggered the
    # Agent — not just the first voice.route.
    try:
        from app.api.routes.voice_ws import _envelope as _ws_envelope
        from app.core.routing import executor as voice_executor
        from app.core.routing.connection import manager as _ws_manager
        from app.core.schemas.canonical import MessageType as _MsgType
        voice_executor.manager = _ws_manager
        voice_executor.envelope_fn = _ws_envelope
        voice_executor.message_type = _MsgType
        logger.info("[Startup] Voice executor globals wired")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, ImportError) as e:
        logger.warning(f"[Startup] Voice executor wiring failed (non-critical): {e}")

    # Migrate legacy deterministic LearnedSkill rows -> macros table (idempotent).
    # Runs after DB init so the macros table exists. Non-fatal: migration errors
    # are logged but do not prevent the server from starting.
    try:
        from app.core.execution.macro.migration import migrate_deterministic_skills
        stats = await migrate_deterministic_skills()
        logger.info(
            "[Startup] Macro migration complete: migrated=%d skipped=%d failed=%d",
            stats.get("migrated", 0),
            stats.get("skipped", 0),
            stats.get("failed", 0),
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.warning(f"[Startup] Macro migration failed (non-critical): {e}")

    yield

    # --- Shutdown ---
    logger.info("Shutting down EvoLoop resources...")

    # 1. Publish Application Stopping Event
    # This triggers all decentalized LifecycleHandlers (EvoCloud, Memory, Indexing, MCP, etc.)
    try:
        from app.core.events.publishers import publish_app_stopping
        await publish_app_stopping()
        logger.info("[Shutdown] APP_STOPPING event published")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
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
