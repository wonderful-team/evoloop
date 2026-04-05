#!/usr/bin/env python3
"""
Start Huey Worker for EvoLoop (Embedded Mode).

Usage:
    python scripts/start_worker.py
    python scripts/start_worker.py --workers=4 --verbose
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    parser = argparse.ArgumentParser(
        description='Start EvoLoop Huey Worker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Start with default settings (2 workers)
    python scripts/start_worker.py
    
    # Start with 4 workers
    python scripts/start_worker.py --workers=4
    
    # Start with verbose logging
    python scripts/start_worker.py --verbose
    
    # Start with custom database path
    python scripts/start_worker.py --db-path=~/.evoloop/custom_queue.db
        """
    )
    
    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=2,
        help='Number of worker threads (default: 2)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Custom database path for Huey (default: ~/.evoloop/task_queue.db)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("EvoLoop Huey Worker Starting...")
    logger.info("=" * 60)
    
    try:
        # Import after setting up logging
        from app.infrastructure.queue.huey_queue import get_huey_scheduler
        from app.core.config import settings
        
        # Get scheduler
        scheduler = get_huey_scheduler()
        huey = scheduler.get_huey()
        
        # Show configuration
        db_path = args.db_path or str(Path(settings.SQLITE_PATH).parent / "task_queue.db")
        logger.info(f"Database: {db_path}")
        logger.info(f"Workers: {args.workers}")
        logger.info(f"Worker Type: thread")
        logger.info("")
        logger.info("Press Ctrl+C to stop")
        logger.info("")
        
        # Import and register all tasks
        logger.info("Registering tasks...")
        
        # Import task modules to register tasks
        try:
            from app.domain.wiki import tasks as wiki_tasks
            logger.info("  - Wiki tasks registered")
        except Exception as e:
            logger.warning(f"  - Wiki tasks: {e}")
        
        try:
            from app.core.engine import tasks as engine_tasks
            logger.info("  - Engine tasks registered")
        except Exception as e:
            logger.warning(f"  - Engine tasks: {e}")
        
        try:
            from app.domain.codebase.indexing import tasks as indexing_tasks
            logger.info("  - Indexing tasks registered")
        except Exception as e:
            logger.warning(f"  - Indexing tasks: {e}")
        
        try:
            from app.core.atlas import tasks as atlas_tasks
            logger.info("  - Atlas tasks registered")
        except Exception as e:
            logger.warning(f"  - Atlas tasks: {e}")
        
        try:
            from app.domain.project import summarizer as project_tasks
            logger.info("  - Project tasks registered")
        except Exception as e:
            logger.warning(f"  - Project tasks: {e}")
        
        try:
            from app.domain.project import sync_tasks
            logger.info("  - Sync tasks registered")
        except Exception as e:
            logger.warning(f"  - Sync tasks: {e}")
        
        logger.info("")
        logger.info("Worker ready!")
        logger.info("")
        
        # Start worker
        from huey.consumer import Consumer
        
        consumer = Consumer(
            huey,
            workers=args.workers,
            worker_type='thread',
            initial_delay=0.1,
            max_delay=60.0,
            backoff=1.15,
            scheduler_interval=1,
            periodic=True,
            check_worker_health=True,
            health_check_interval=10,
        )
        
        consumer.run()
        
    except KeyboardInterrupt:
        logger.info("")
        logger.info("Shutting down...")
        logger.info("Goodbye!")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
