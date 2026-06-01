#!/usr/bin/env python3
"""
Standalone Huey Worker Process.

Usage:
    python -m scripts.run_worker
    python -m scripts.run_worker --workers=4 --verbose

Environment:
    EMBEDDED_MODE=true|false  true→Huey, false→Celery
"""

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

# Add parent directory to path
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# Configure logging before importing app modules
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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


def run_huey_worker(workers: int = 2, verbose: bool = False):
    """Run Huey worker as standalone process."""
    from app.infrastructure.queue.huey_queue import get_huey_scheduler
    from huey.consumer import Consumer
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        # Ensure task-related loggers are verbose
        for name in ['app.core.engine.tasks', 'app.infrastructure.queue']:
            logging.getLogger(name).setLevel(logging.DEBUG)
    else:
        # Even in non-verbose mode, ensure we see task errors
        logging.getLogger('app.core.engine.tasks').setLevel(logging.INFO)
        logging.getLogger('app.infrastructure.queue').setLevel(logging.INFO)
    
    logger.info("=" * 60)
    logger.info("EvoLoop Task Queue Worker")
    logger.info("=" * 60)
    logger.info(f"Backend: huey (embedded mode)")
    logger.info(f"Workers: {workers}")
    logger.info(f"Worker Type: thread (SQLite compatible)")
    logger.info("=" * 60)
    
    # Get Huey scheduler
    scheduler = get_huey_scheduler()
    
    # Pre-load all task modules before starting consumer
    # This ensures tasks are registered in the worker process
    logger.info("[Worker] Pre-loading task modules...")
    scheduler._preload_task_modules()
    
    huey = scheduler.get_huey()
    
    logger.info(f"[Worker] Initializing Huey Consumer...")
    
    # Create consumer
    consumer = Consumer(
        huey,
        workers=workers,
        worker_type='thread',
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
    
    # Ensure Python root logger has a handler before Celery hijacks it.
    # Celery defaults to hijacking root logger; we disable that so our
    # basicConfig handler (set at module level) survives and forwards all
    # application loggers (app.core.engine.*, etc.) to the worker output.
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
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
    # Prevent Celery from removing our root logger handler
    scheduler.conf.worker_hijack_root_logger = False
    scheduler.worker_main(argv=argv)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="EvoLoop Task Queue Worker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.run_worker              # Start with default settings
  python -m scripts.run_worker --workers=4  # Start with 4 workers
  python -m scripts.run_worker --verbose    # Enable debug logging

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
