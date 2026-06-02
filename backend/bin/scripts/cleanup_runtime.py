import asyncio
import logging
import redis
from app.core.config import settings
from app.celery_app import celery_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_runtime():
    logger.info("STARTING RUNTIME CLEANUP")

    # 1. Redis Flush
    logger.info(f"Connecting to Redis at {settings.REDIS_URL}...")
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.flushdb()
        logger.info("Redis FLUSHDB executed successfully. Cache cleared.")
    except Exception as e:
        logger.error(f"Failed to flush Redis: {e}")

    # 2. Celery Purge
    logger.info("Purging Celery queues...")
    try:
        # inspect() might be needed to see what's there, but purge() is nuclear.
        purged_count = celery_app.control.purge()
        logger.info(f"Celery queues purged. Removed {purged_count} pending tasks.")
    except Exception as e:
        logger.error(f"Failed to purge Celery: {e}")

    logger.info("RUNTIME CLEANUP COMPLETE.")

if __name__ == "__main__":
    cleanup_runtime()
