import asyncio
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

logging.basicConfig(level=settings.LOG_LEVEL)
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001

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
        logger.warning(f"Failed to reload SharedState persisted project: {e}")

    # Channel Registry - register built-in transports (SSE + Mobile)
    try:
        from app.core.channel import register_default_channels

        register_default_channels()
        logger.info("Channel registry initialized (SSE + Mobile).")
    except Exception as e:
        logger.warning(f"Failed to initialize Channel registry: {e}")

    # Agent Awakening - Discovery & Lifecycle Handlers
    try:
        from app.core.events.discovery import auto_discover_handlers

        auto_discover_handlers()
        logger.info("Discovery and registration of all domain lifecycle handlers complete.")
    except Exception as e:
        logger.warning(f"Agent Awakening/Discovery failed (non-critical): {e}")

    # Publish Application Started Event
    from app.core.events.publishers import publish_app_started

    await publish_app_started(startup_time)
    logger.info("[Startup] APP_STARTED event published")

    # --- 值守/自主调度：由 API 进程驱动 ---
    # 值守 Agent 会话跑在 API 进程 → 事件直接进 API 的本地 broker → SSE 实时到前端
    # （worker 进程的 broker 是进程内、且未注册 sse 渠道，值守跑在 worker 前端收不到实时事件）。
    scheduler_task: asyncio.Task | None = None
    try:
        async def _scheduler_loop():
            from app.infrastructure.scheduler.service import SchedulerService

            # 先 tick 后 sleep：启动即补扫 —— tick 按 next_run_at <= now 扫描，
            # 进程离线期间到期的任务在重启后首轮全部命中（离线补跑语义，
            # 依赖此顺序，勿改为先 sleep）。
            while True:
                try:
                    await SchedulerService.tick()
                except Exception:
                    logger.exception("[Scheduler] tick 执行失败")
                await asyncio.sleep(60)

        scheduler_task = asyncio.create_task(_scheduler_loop())
        logger.info("[Startup] 值守/自主调度循环已启动 (API 进程)")
    except Exception as e:
        logger.warning(f"[Startup] 调度循环启动失败 (非关键): {e}")

    yield

    # --- Shutdown ---
    logger.info("Shutting down EvoLoop resources...")

    # 停止值守/自主调度循环
    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] 调度循环已停止")

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
