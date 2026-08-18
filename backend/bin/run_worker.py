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
from pathlib import Path

# Add parent directory to path
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# Configure logging before importing app modules
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
        # Ensure task-related loggers are verbose
        for name in ["app.core.engine.tasks", "app.infrastructure.queue"]:
            logging.getLogger(name).setLevel(logging.DEBUG)
    else:
        # Even in non-verbose mode, ensure we see task errors
        logging.getLogger("app.core.engine.tasks").setLevel(logging.INFO)
        logging.getLogger("app.infrastructure.queue").setLevel(logging.INFO)

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

    # Register the WeCom duty channel as an OUTPUT channel (reusing the voice
    # MessageBlock → output-channel pipeline so Supervisor can send a brief
    # reassurance reply before routing a task to Worker). The duty poll path
    # instantiates WeComDutyChannel lazily; the output-channel registration must
    # exist in the worker process where duty runs (worker does not publish
    # APP_STARTED, so register_default_channels() in main.py never runs here).
    logger.info("[Worker] Registering wecom_duty output channel...")
    try:
        from app.core.channel import channel_registry
        from app.core.channel.duty.wecom.channel import WeComDutyChannel

        channel_registry.register(WeComDutyChannel())
        logger.info("[Worker] wecom_duty output channel registered")
    except Exception as e:
        logger.warning(f"[Worker] Failed to register wecom_duty output channel: {e}")

    # Pre-load MCP servers inside the Huey worker thread (not the main thread).
    # huey's on_startup hooks run in each worker thread's initialize(), so the
    # event loop created here is the SAME loop that _run_async_task reuses for
    # tasks. MCP sessions bound here are therefore used in-loop by Agent runs
    # (no cross-loop AsyncExitStack hangs).
    huey = scheduler.get_huey()

    @huey.on_startup(name="preload_mcp_servers")
    def _preload_mcp():
        import asyncio as _asyncio

        logger.info("[Worker] Pre-loading MCP servers (worker thread)...")
        try:
            from app.core.mcp import mcp_client_manager

            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)

            async def _connect_mcp():
                from app.infrastructure.database.resource_manager import (
                    db_resource_manager,
                )

                await db_resource_manager.initialize(create_tables=False,
                                                     seed_data=False)
                # 恢复持久化的 SharedState project_id（SSOT：后端重启后仍用上次选择）
                from app.core.state import shared_state

                await shared_state.reload_persisted()
                if not mcp_client_manager._configs:
                    results = await mcp_client_manager.connect_all()
                    ok = sum(1 for r in results if r.success)
                    logger.info(f"[Worker] MCP servers connected: {ok}/{len(results)}")

            loop.run_until_complete(_connect_mcp())
        except Exception as e:
            logger.warning(f"[Worker] Failed to pre-load MCP servers: {e}")

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
