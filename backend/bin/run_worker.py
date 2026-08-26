#!/usr/bin/env python3
"""
Standalone Huey Worker Process.

Usage:
    python -m bin.run_worker
    python -m bin.run_worker --workers=4 --verbose

Environment:
    EMBEDDED_MODE=true|false  true→Huey, false→Celery
"""

import argparse
import asyncio
import logging
import signal
import sys
import threading
from pathlib import Path

# Add parent directory to path
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# Configure logging before importing app modules
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("worker")


def setup_signal_handlers(consumer):
    """Setup graceful shutdown on SIGINT/SIGTERM."""

    def signal_handler(signum, frame):
        logger.info(f"[Worker] Received signal {signum}, shutting down gracefully...")
        if consumer:
            consumer.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def run_huey_worker(workers: int = 1, verbose: bool = False):
    """Run Huey worker as standalone process."""
    from huey.consumer import Consumer

    from app.infrastructure.queue.huey_queue import get_huey_scheduler

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("app").setLevel(logging.DEBUG)
        # Ensure task-related loggers are verbose
        for name in ["app.core.engine.tasks", "app.infrastructure.queue"]:
            logging.getLogger(name).setLevel(logging.DEBUG)
    else:
        # 非 verbose 时也保证任务日志可见：级别跟随 LOG_LEVEL（默认 INFO）
        from app.core.config import settings

        _task_level = getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO)
        logging.getLogger("app.core.engine.tasks").setLevel(_task_level)
        logging.getLogger("app.infrastructure.queue").setLevel(_task_level)

    logger.info("=" * 60)
    logger.info("EvoLoop Task Queue Worker")
    logger.info("=" * 60)
    logger.info("Backend: huey (embedded mode)")
    logger.info(f"Workers: {workers}")
    logger.info("Worker Type: thread (SQLite compatible)")
    logger.info("=" * 60)

    # Get Huey scheduler
    scheduler = get_huey_scheduler()

    # Pre-load all task modules before starting consumer
    # This ensures tasks are registered in the worker process
    logger.info("[Worker] Pre-loading task modules...")
    scheduler._preload_task_modules()

    # Warm up Embedder model so worker threads share the cached instance.
    logger.info("[Worker] Pre-loading embedding model...")
    try:
        from app.infrastructure.embeddings.factory import EmbedderFactory
        from app.infrastructure.embeddings.local import LocalEmbedder

        embedder = EmbedderFactory.get_embedder()
        # Force the actual model load now so tasks never pay the cost.
        if isinstance(embedder, LocalEmbedder):
            asyncio.run(embedder._get_model())
        logger.info(f"[Worker] Embedding model loaded: {type(embedder).__name__}")
    except Exception as e:
        logger.warning(f"[Worker] Failed to pre-load embedding model: {e}")

    # Pre-register native tools at startup (matching API process behavior via
    # APP_STARTED → ToolsLifecycleSubscriber). Worker does not publish
    # APP_STARTED, so tools would otherwise be lazily scanned on the first
    # Agent run, mixing registration cost into the duty poll path.
    logger.info("[Worker] Pre-registering tools...")
    try:
        from app.core.tools.registry import _ensure_scanned

        _ensure_scanned()
        logger.info("[Worker] Tools pre-registered")
    except Exception as e:
        logger.warning(f"[Worker] Failed to pre-register tools: {e}")

    # 注：wecom_duty 输出渠道注册已在值守搬至 API 进程后移除（run_worker.py 历史代码）。
    # 值守 Agent 在 API 进程运行，wecom_duty 由 app.main.lifespan 注册；worker 不再需要。

    # 创建 worker 线程的持久事件循环（on_startup hook）并持续驱动。
    huey = scheduler.get_huey()

    @huey.on_startup(name="setup_worker_event_loop")
    def _setup_worker_loop():
        """创建 worker 线程的持久事件循环并持续驱动。

        值守已搬至 API 进程（MCP 初始化/连接也随之搬到 API），worker 不再需要 MCP。
        这里只保留事件循环基础设施：_run_async_task 复用此 loop + 后台线程
        run_forever 持续驱动，供 worker 上的非值守异步任务/Agent 会话使用。
        """
        logger.info("[Worker] Setting up worker event loop...")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _init():
                from app.infrastructure.database.resource_manager import db_resource_manager

                await db_resource_manager.initialize(create_tables=False,
                                                     seed_data=False)
                # 恢复持久化的 SharedState project_id（SSOT：后端重启后仍用上次选择）
                from app.core.state import shared_state

                await shared_state.reload_persisted()

            loop.run_until_complete(_init())

            # 关键：让该事件循环**持续运行**。否则 loop 只在每个 Huey 任务执行期间
            # 由 run_until_complete 驱动，任务间隙循环空闲——后台 asyncio 任务
            # （如非值守 Agent 会话的 LLM 流式调用）会被冻结、拖慢上百倍。
            def _drive_loop_forever():
                asyncio.set_event_loop(loop)
                loop.run_forever()

            threading.Thread(
                target=_drive_loop_forever,
                name="worker-event-loop",
                daemon=True,
            ).start()
            logger.info("[Worker] Worker event loop running continuously (run_forever)")
        except Exception as e:
            logger.warning(f"[Worker] Failed to setup worker event loop: {e}")

    logger.info("[Worker] Initializing Huey Consumer...")

    # Create consumer
    consumer = Consumer(
        huey,
        workers=workers,
        worker_type="thread",
        initial_delay=0.1,
        max_delay=60.0,
        backoff=1.15,
        scheduler_interval=1,
        periodic=True,  # Enable periodic tasks
        check_worker_health=True,
        health_check_interval=10,
    )

    logger.info(f"[Worker] Consumer created with {workers} workers")

    # Setup signal handlers for graceful shutdown
    setup_signal_handlers(consumer)

    logger.info("[Worker] Starting consumer (Press Ctrl+C to stop)...")
    logger.info("-" * 60)

    try:
        # Run consumer (blocks until stopped)
        consumer.run()
    except KeyboardInterrupt:
        logger.info("[Worker] Keyboard interrupt received")
    finally:
        logger.info("[Worker] Shutting down...")
        consumer.stop()
        logger.info("[Worker] Stopped")


def run_celery_worker(workers: int = 2, verbose: bool = False):
    """Run Celery worker as standalone process."""
    from app.infrastructure.queue.factory import get_scheduler

    logger.info("=" * 60)
    logger.info("EvoLoop Celery Worker")
    logger.info("=" * 60)
    logger.info(f"Workers: {workers}")

    argv = [
        "worker",
        "--loglevel=debug" if verbose else "--loglevel=info",
        f"--concurrency={workers}",
        "--queues=celery",
    ]

    logger.info(f"[Worker] Starting Celery with args: {argv}")
    scheduler = get_scheduler()
    scheduler.worker_main(argv=argv)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="EvoLoop Task Queue Worker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m bin.run_worker              # Start with default settings
  python -m bin.run_worker --workers=4  # Start with 4 workers
  python -m bin.run_worker --verbose    # Enable debug logging

Based on EMBEDDED_MODE setting:
  EMBEDDED_MODE=true  → Huey worker (in-process, SQLite)
  EMBEDDED_MODE=false → Celery worker (requires Redis)
        """
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of worker threads/processes (default: 2)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (debug) logging"
    )

    args = parser.parse_args()

    # Import settings after setting up logging
    from app.core.config import settings

    if settings.EMBEDDED_MODE:
        logger.info("[Worker] Embedded mode: starting Huey worker")
        run_huey_worker(args.workers, args.verbose)
    else:
        logger.info("[Worker] Full mode: starting Celery worker")
        run_celery_worker(args.workers, args.verbose)


if __name__ == "__main__":
    main()
