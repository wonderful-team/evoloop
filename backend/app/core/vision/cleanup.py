"""
Storage Cleanup Task - Periodic cleanup of expired screenshots and screen recordings.

Can be run as:
1. Celery periodic task
2. CLI command
3. Startup cleanup
"""

import logging
from datetime import datetime

from app.core.vision.storage import screenshot_storage, screen_recording_storage

logger = logging.getLogger(__name__)


def cleanup_screenshots(dry_run: bool = False) -> dict:
    """
    Clean up expired screenshots based on retention policy.

    Args:
        dry_run: If True, only report what would be cleaned without deleting

    Returns:
        Cleanup statistics
    """
    logger.info(f"[ScreenshotCleanup] Starting {'dry run' if dry_run else 'cleanup'} at {datetime.now()}")

    stats = screenshot_storage.cleanup_expired(dry_run=dry_run)

    total_files = sum(stats.values())
    logger.info(f"[ScreenshotCleanup] {'Would clean' if dry_run else 'Cleaned'} {total_files} files: {stats}")

    return {
        "dry_run": dry_run,
        "files_cleaned": stats,
        "total": total_files,
        "timestamp": datetime.now().isoformat(),
    }


def cleanup_screen_recordings(dry_run: bool = False) -> dict:
    """
    Clean up expired screen recordings based on retention policy.

    Args:
        dry_run: If True, only report what would be cleaned without deleting

    Returns:
        Cleanup statistics
    """
    logger.info(f"[ScreenRecordingCleanup] Starting {'dry run' if dry_run else 'cleanup'} at {datetime.now()}")

    stats = screen_recording_storage.cleanup_expired(dry_run=dry_run)

    total_files = sum(stats.values())
    logger.info(f"[ScreenRecordingCleanup] {'Would clean' if dry_run else 'Cleaned'} {total_files} items: {stats}")

    return {
        "dry_run": dry_run,
        "items_cleaned": stats,
        "total": total_files,
        "timestamp": datetime.now().isoformat(),
    }


def cleanup_all(dry_run: bool = False) -> dict:
    """
    Clean up all expired storage (screenshots + recordings).

    Args:
        dry_run: If True, only report what would be cleaned without deleting

    Returns:
        Combined cleanup statistics
    """
    logger.info(f"[StorageCleanup] Starting {'dry run' if dry_run else 'full cleanup'} at {datetime.now()}")

    screenshot_stats = cleanup_screenshots(dry_run)
    recording_stats = cleanup_screen_recordings(dry_run)

    return {
        "dry_run": dry_run,
        "screenshots": screenshot_stats,
        "recordings": recording_stats,
        "total_cleaned": screenshot_stats["total"] + recording_stats["total"],
        "timestamp": datetime.now().isoformat(),
    }


def get_storage_report() -> dict:
    """Get full storage statistics report."""
    screenshot_stats = screenshot_storage.get_stats()
    recording_stats = screen_recording_storage.get_stats()

    total_screenshot_files = sum(s["file_count"] for s in screenshot_stats.values())
    total_screenshot_size_mb = sum(s["total_size_mb"] for s in screenshot_stats.values())

    total_recording_files = sum(s["file_count"] for s in recording_stats.values())
    total_recording_size_mb = sum(s["total_size_mb"] for s in recording_stats.values())

    return {
        "screenshots": {
            "categories": screenshot_stats,
            "summary": {
                "total_files": total_screenshot_files,
                "total_size_mb": round(total_screenshot_size_mb, 2),
                "total_size_gb": round(total_screenshot_size_mb / 1024, 2),
            },
        },
        "recordings": {
            "categories": recording_stats,
            "summary": {
                "total_files": total_recording_files,
                "total_size_mb": round(total_recording_size_mb, 2),
                "total_size_gb": round(total_recording_size_mb / 1024, 2),
            },
            "limits": screen_recording_storage.check_storage_limits(),
        },
        "total": {
            "total_files": total_screenshot_files + total_recording_files,
            "total_size_gb": round((total_screenshot_size_mb + total_recording_size_mb) / 1024, 2),
        },
        "timestamp": datetime.now().isoformat(),
    }


# Celery task wrapper
try:
    # Unified task queue (Huey in embedded mode, Celery in full mode)
    from app.infrastructure.queue.factory import get_scheduler

    # Get scheduler instance
    _task_scheduler = get_scheduler()

    # Create task decorator
    def _task(name, **kwargs):
        def decorator(f):
            return _task_scheduler.task(f, name=name, **kwargs)
        return decorator

    @_task(name="app.core.vision.cleanup_screenshots")
    def cleanup_screenshots_task(dry_run: bool = False) -> dict:
        """Celery task for periodic screenshot cleanup."""
        return cleanup_screenshots(dry_run=dry_run)

    @_task(name="app.core.vision.cleanup_screen_recordings")
    def cleanup_screen_recordings_task(dry_run: bool = False) -> dict:
        """Celery task for periodic screen recording cleanup."""
        return cleanup_screen_recordings(dry_run=dry_run)

    @_task(name="app.core.vision.cleanup_all_storage")
    def cleanup_all_storage_task(dry_run: bool = False) -> dict:
        """Celery task for periodic cleanup of all storage."""
        return cleanup_all(dry_run=dry_run)

except ImportError:
    logger.debug("[StorageCleanup] Celery not available, task not registered")
    cleanup_screenshots_task = None
    cleanup_screen_recordings_task = None
    cleanup_all_storage_task = None
