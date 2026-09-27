"""
Screenshot & Screen Recording Storage Manager - Unified hierarchical storage.

分层存储管理器：
Screenshots (截图):
- temp: 临时截图，用于即时OCR/处理，自动清理
- atlas: Atlas学习截图，按应用存储，用于知识图谱构建
- debug: 调试截图，用于故障排查
- dataset: 数据集截图，用于IL训练数据收集

Screen Recordings (屏幕录制):
- recordings: 屏幕录制视频
- frames: 从视频中提取的帧
"""

import logging
import os
import shutil
from datetime import datetime, timedelta
from enum import Enum

from app.core.config import settings
from app.core.file import ensure_dir
from app.infrastructure.vision.types import PlatformType

logger = logging.getLogger(__name__)


class ScreenshotPurpose(Enum):
    """Screenshot storage purpose categories."""

    TEMP = "temp"  # 临时使用（OCR、即时处理）
    ATLAS = "atlas"  # Atlas知识图谱学习
    DEBUG = "debug"  # 调试/错误排查
    DATASET = "dataset"  # 训练数据集


class ScreenshotStorage:
    """
    Unified manager for hierarchical screenshot storage.

    Usage:
        storage = ScreenshotStorage()

        # Store with purpose
        path = storage.save_screenshot(image_bytes, purpose="atlas", bundle_id="com.example.app")

        # Get path for saving (legacy compatibility)
        path = storage.get_path(purpose="temp", platform="android")
    """

    PURPOSE_CONFIG = {
        ScreenshotPurpose.TEMP: {
            "dir": lambda: settings.SCREENSHOTS_TEMP_DIR,
            "retention_days": lambda: settings.SCREENSHOT_TEMP_RETENTION_DAYS,
        },
        ScreenshotPurpose.ATLAS: {
            "dir": lambda: settings.SCREENSHOTS_ATLAS_DIR,
            "retention_days": lambda: settings.SCREENSHOT_ATLAS_RETENTION_DAYS,
        },
        ScreenshotPurpose.DEBUG: {
            "dir": lambda: settings.SCREENSHOTS_DEBUG_DIR,
            "retention_days": lambda: settings.SCREENSHOT_DEBUG_RETENTION_DAYS,
        },
        ScreenshotPurpose.DATASET: {
            "dir": lambda: settings.SCREENSHOTS_DATASET_DIR,
            "retention_days": lambda: settings.SCREENSHOT_DATASET_RETENTION_DAYS,
        },
    }

    def __init__(self):
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure all screenshot directories exist."""
        for purpose in ScreenshotPurpose:
            path = self._get_base_dir(purpose)
            ensure_dir(path)
            logger.debug(f"[ScreenshotStorage] Ensured directory: {path}")

    def _get_base_dir(self, purpose: ScreenshotPurpose) -> str:
        """Get base directory for a purpose."""
        return self.PURPOSE_CONFIG[purpose]["dir"]()

    def _generate_filename(
        self,
        platform: str,
        bundle_id: str | None = None,
        suffix: str | None = None,
        ext: str = "png",
    ) -> str:
        """Generate organized filename with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

        # Build filename parts
        parts = [platform, timestamp]

        if bundle_id:
            # Sanitize bundle_id for filesystem
            safe_bundle = bundle_id.replace(".", "_").replace("/", "_")
            parts.insert(1, safe_bundle)

        if suffix:
            parts.append(suffix)

        return f"{'_'.join(parts)}.{ext}"

    def get_path(
        self,
        purpose: ScreenshotPurpose = ScreenshotPurpose.TEMP,
        platform: PlatformType = PlatformType.MACOS,
        bundle_id: str | None = None,
        suffix: str | None = None,
        create_dir: bool = True,
    ) -> str:
        """
        Get a file path for saving a screenshot.

        Args:
            purpose: Storage category (temp/atlas/debug/dataset)
            platform: Target platform
            bundle_id: App identifier (for atlas organization)
            suffix: Additional identifier
            ensure_dir: Create directory if not exists

        Returns:
            Full path for the screenshot file
        """
        purpose_enum = ScreenshotPurpose(purpose)
        base_dir = self._get_base_dir(purpose_enum)

        # For atlas, organize by bundle_id and date
        if purpose_enum == ScreenshotPurpose.ATLAS and bundle_id:
            date_folder = datetime.now().strftime("%Y%m%d")
            safe_bundle = bundle_id.replace(".", "_").replace("/", "_")
            dir_path = os.path.join(base_dir, safe_bundle, date_folder)
        else:
            # For others, organize by date only
            date_folder = datetime.now().strftime("%Y%m%d")
            dir_path = os.path.join(base_dir, date_folder)

        if create_dir:
            ensure_dir(dir_path)

        filename = self._generate_filename(platform, bundle_id, suffix)
        return os.path.join(dir_path, filename)

    def save_screenshot(
        self,
        image_data: bytes,
        purpose: ScreenshotPurpose = ScreenshotPurpose.TEMP,
        platform: PlatformType = PlatformType.MACOS,
        bundle_id: str | None = None,
        suffix: str | None = None,
    ) -> str:
        """
        Save screenshot bytes to appropriate location.

        Args:
            image_data: Raw image bytes
            purpose: Storage category
            platform: Target platform
            bundle_id: App identifier
            suffix: Additional identifier

        Returns:
            Path to saved file
        """
        filepath = self.get_path(purpose, platform, bundle_id, suffix)

        try:
            with open(filepath, "wb") as f:
                f.write(image_data)
            logger.debug(f"[ScreenshotStorage] Saved {purpose} screenshot: {filepath}")
            return filepath
        except Exception as e:
            logger.exception(f"[ScreenshotStorage] Failed to save screenshot: {e}")
            raise

    def cleanup_expired(self, dry_run: bool = False) -> dict[str, int]:
        """
        Clean up expired screenshots based on retention policy.

        Args:
            dry_run: If True, only count without deleting

        Returns:
            Stats of cleaned files by purpose
        """
        stats = {purpose.value: 0 for purpose in ScreenshotPurpose}
        now = datetime.now()

        for purpose in ScreenshotPurpose:
            base_dir = self._get_base_dir(purpose)
            retention_days = self.PURPOSE_CONFIG[purpose]["retention_days"]()
            cutoff = now - timedelta(days=retention_days)

            if not os.path.exists(base_dir):
                continue

            for root, _dirs, files in os.walk(base_dir):
                for file in files:
                    if not file.endswith((".png", ".jpg", ".jpeg")):
                        continue

                    filepath = os.path.join(root, file)
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                        if mtime < cutoff:
                            stats[purpose.value] += 1
                            if not dry_run:
                                os.remove(filepath)
                                logger.debug(f"[ScreenshotStorage] Cleaned: {filepath}")
                    except Exception as e:
                        logger.warning(f"[ScreenshotStorage] Cleanup error for {filepath}: {e}", exc_info=True)

            # Clean empty directories
            if not dry_run:
                self._remove_empty_dirs(base_dir)

        total = sum(stats.values())
        action = "Would clean" if dry_run else "Cleaned"
        logger.info(f"[ScreenshotStorage] {action} {total} expired screenshots: {stats}")
        return stats

    def _remove_empty_dirs(self, base_dir: str):
        """Remove empty directories recursively."""
        for root, _dirs, _files in os.walk(base_dir, topdown=False):
            for dir_name in _dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if os.path.exists(dir_path) and not os.listdir(dir_path):
                        os.rmdir(dir_path)
                        logger.debug(f"[ScreenshotStorage] Removed empty dir: {dir_path}")
                except Exception as e:
                    logger.debug(f"Storage error: {e}", exc_info=True)

    def get_stats(self) -> dict[str, dict]:
        """Get storage statistics for all purposes."""
        stats = {}

        for purpose in ScreenshotPurpose:
            base_dir = self._get_base_dir(purpose)
            total_size = 0
            file_count = 0

            if os.path.exists(base_dir):
                for root, _dirs, files in os.walk(base_dir):
                    for file in files:
                        if file.endswith((".png", ".jpg", ".jpeg")):
                            filepath = os.path.join(root, file)
                            try:
                                total_size += os.path.getsize(filepath)
                                file_count += 1
                            except Exception as e:
                                logger.debug(f"Storage error: {e}", exc_info=True)

            retention = self.PURPOSE_CONFIG[purpose]["retention_days"]()
            stats[purpose.value] = {
                "directory": base_dir,
                "file_count": file_count,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "retention_days": retention,
            }

        return stats



# Singleton instance
screenshot_storage = ScreenshotStorage()


def get_screenshot_path(
    purpose: ScreenshotPurpose = ScreenshotPurpose.TEMP,
    platform: PlatformType = PlatformType.MACOS,
    bundle_id: str | None = None,
    suffix: str | None = None,
) -> str:
    """Convenience function to get screenshot path."""
    return screenshot_storage.get_path(purpose, platform, bundle_id, suffix)


def save_screenshot(
    image_data: bytes,
    purpose: ScreenshotPurpose = ScreenshotPurpose.TEMP,
    platform: PlatformType = PlatformType.MACOS,
    bundle_id: str | None = None,
    suffix: str | None = None,
) -> str:
    """Convenience function to save screenshot."""
    return screenshot_storage.save_screenshot(image_data, purpose, platform, bundle_id, suffix)

# ============================================================================
# Screen Recording Storage (屏幕录制存储)
# ============================================================================


class ScreenRecordingStorage:
    """
    Unified manager for screen recording storage.

    Manages:
    - Video files (.mp4) from screen recordings
    - Extracted frames from videos
    - Automatic cleanup based on retention policy

    Usage:
        storage = ScreenRecordingStorage()

        # Get path for new recording
        path = storage.get_recording_path(session_id="xxx")

        # Get path for extracted frames
        frame_path = storage.get_frame_path(session_id="xxx", timestamp_ms=1500)

        # Cleanup old recordings
        storage.cleanup_expired()
    """

    def __init__(self):
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure all recording directories exist."""
        ensure_dir(settings.SCREEN_RECORDINGS_DIR)
        ensure_dir(settings.SCREEN_RECORDING_FRAMES_DIR)
        logger.debug("[ScreenRecordingStorage] Ensured directories")

    def get_recording_path(
        self,
        session_id: str | None = None,
        timestamp: int | None = None,
        ext: str = "mp4",
        create_dir: bool = True,
    ) -> str:
        """
        Get a file path for saving a screen recording.

        Args:
            session_id: Recording session ID for organization
            timestamp: Unix timestamp (default: current time)
            ext: File extension
            ensure_dir: Create directory if not exists

        Returns:
            Full path for the recording file
        """
        if timestamp is None:
            timestamp = int(datetime.now().timestamp() * 1000)

        # Organize by date
        date_folder = datetime.now().strftime("%Y%m%d")
        dir_path = os.path.join(settings.SCREEN_RECORDINGS_DIR, date_folder)

        if create_dir:
            ensure_dir(dir_path)

        # Include session_id in filename if provided
        if session_id:
            filename = f"recording_{session_id}_{timestamp}.{ext}"
        else:
            filename = f"recording_{timestamp}.{ext}"

        return os.path.join(dir_path, filename)

    def get_frame_path(
        self,
        session_id: str,
        timestamp_ms: int,
        ext: str = "png",
        create_dir: bool = True,
    ) -> str:
        """
        Get a file path for saving an extracted frame.

        Args:
            session_id: Recording session ID
            timestamp_ms: Frame timestamp in milliseconds
            ext: File extension
            ensure_dir: Create directory if not exists

        Returns:
            Full path for the frame file
        """
        # Organize frames by session
        dir_path = os.path.join(settings.SCREEN_RECORDING_FRAMES_DIR, session_id)

        if create_dir:
            ensure_dir(dir_path)

        filename = f"frame_{timestamp_ms}.{ext}"
        return os.path.join(dir_path, filename)

    def get_frames_dir(self, session_id: str, create_dir: bool = True) -> str:
        """
        Get the directory for extracted frames of a session.

        Args:
            session_id: Recording session ID
            ensure_dir: Create directory if not exists

        Returns:
            Path to the frames directory
        """
        dir_path = os.path.join(settings.SCREEN_RECORDING_FRAMES_DIR, session_id)
        if create_dir:
            ensure_dir(dir_path)
        return dir_path

    def cleanup_expired(self, dry_run: bool = False) -> dict[str, int]:
        """
        Clean up expired recordings and frames based on retention policy.

        Args:
            dry_run: If True, only count without deleting

        Returns:
            Stats of cleaned files by type
        """
        stats = {"videos": 0, "frames": 0}
        now = datetime.now()
        cutoff = now - timedelta(days=settings.SCREEN_RECORDING_RETENTION_DAYS)

        # Clean video files
        if os.path.exists(settings.SCREEN_RECORDINGS_DIR):
            for root, _dirs, files in os.walk(settings.SCREEN_RECORDINGS_DIR):
                for file in files:
                    if not file.endswith((".mp4", ".mov", ".avi", ".mkv")):
                        continue

                    filepath = os.path.join(root, file)
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                        if mtime < cutoff:
                            stats["videos"] += 1
                            if not dry_run:
                                os.remove(filepath)
                                logger.debug(f"[ScreenRecordingStorage] Cleaned video: {filepath}")
                    except Exception as e:
                        logger.warning(f"[ScreenRecordingStorage] Cleanup error for {filepath}: {e}", exc_info=True)

            # Clean empty directories
            if not dry_run:
                self._remove_empty_dirs(settings.SCREEN_RECORDINGS_DIR)

        # Clean frame directories
        if os.path.exists(settings.SCREEN_RECORDING_FRAMES_DIR):
            for session_dir in os.listdir(settings.SCREEN_RECORDING_FRAMES_DIR):
                session_path = os.path.join(settings.SCREEN_RECORDING_FRAMES_DIR, session_dir)
                if not os.path.isdir(session_path):
                    continue

                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(session_path))
                    if mtime < cutoff:
                        # Count files in directory
                        file_count = sum(1 for _, _, files in os.walk(session_path) for f in files)
                        stats["frames"] += file_count
                        if not dry_run:
                            shutil.rmtree(session_path)
                            logger.debug(f"[ScreenRecordingStorage] Cleaned frames dir: {session_path}")
                except Exception as e:
                    logger.warning(f"[ScreenRecordingStorage] Cleanup error for {session_path}: {e}", exc_info=True)

        total = sum(stats.values())
        action = "Would clean" if dry_run else "Cleaned"
        logger.info(f"[ScreenRecordingStorage] {action} {total} expired items: {stats}")
        return stats

    def _remove_empty_dirs(self, base_dir: str):
        """Remove empty directories recursively using unified traverser."""
        from app.core.file import FileTraverser, TraverseOptions

        options = TraverseOptions(include_dirs=True, follow_ignore=False)
        # We need bottom-up but walk is top-down.
        # Actually, we can just get all dirs and sort by depth descending.
        dirs = []
        for path in FileTraverser.walk(base_dir, options):
            if os.path.isdir(path):
                dirs.append(path)
        # Sort by depth descending (longest paths first)
        dirs.sort(key=lambda x: x.count(os.sep), reverse=True)
        for dir_path in dirs:
            try:
                # Check if empty using standardized list_entries
                entries = list(FileTraverser.list_entries(dir_path, follow_ignore=False))
                if not entries:
                    os.rmdir(dir_path)
                    logger.debug(f"[ScreenRecordingStorage] Removed empty dir: {dir_path}")
            except Exception as e:
                logger.debug(f"Storage error: {e}", exc_info=True)

    def get_stats(self) -> dict[str, dict]:
        """Get storage statistics for recordings."""
        stats = {
            "videos": {
                "directory": settings.SCREEN_RECORDINGS_DIR,
                "file_count": 0,
                "total_size_mb": 0,
            },
            "frames": {
                "directory": settings.SCREEN_RECORDING_FRAMES_DIR,
                "file_count": 0,
                "total_size_mb": 0,
            },
        }

        from app.core.file import FileTraverser, TraverseOptions

        no_ignore_options = TraverseOptions(follow_ignore=False)

        # Count videos
        if os.path.exists(settings.SCREEN_RECORDINGS_DIR):
            for filepath in FileTraverser.walk(settings.SCREEN_RECORDINGS_DIR, no_ignore_options):
                if filepath.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
                    try:
                        stats["videos"]["total_size_mb"] += os.path.getsize(filepath) / (1024 * 1024)
                        stats["videos"]["file_count"] += 1
                    except Exception as e:
                        logger.debug(f"Storage error: {e}", exc_info=True)

        # Count frames
        if os.path.exists(settings.SCREEN_RECORDING_FRAMES_DIR):
            for filepath in FileTraverser.walk(settings.SCREEN_RECORDING_FRAMES_DIR, no_ignore_options):
                if filepath.lower().endswith((".png", ".jpg", ".jpeg")):
                    try:
                        stats["frames"]["total_size_mb"] += os.path.getsize(filepath) / (1024 * 1024)
                        stats["frames"]["file_count"] += 1
                    except Exception as e:
                        logger.debug(f"Storage error: {e}", exc_info=True)

        # Round sizes
        for key in stats:
            stats[key]["total_size_mb"] = round(stats[key]["total_size_mb"], 2)
            stats[key]["retention_days"] = settings.SCREEN_RECORDING_RETENTION_DAYS

        return stats

    def check_storage_limits(self) -> dict[str, any]:
        """
        Check if storage limits are exceeded.

        Returns:
            Dict with limit status and details
        """
        stats = self.get_stats()
        total_size_gb = (stats["videos"]["total_size_mb"] + stats["frames"]["total_size_mb"]) / 1024

        result = {
            "total_size_gb": round(total_size_gb, 2),
            "max_size_gb": settings.SCREEN_RECORDING_MAX_SIZE_GB,
            "size_limit_exceeded": total_size_gb > settings.SCREEN_RECORDING_MAX_SIZE_GB,
            "videos_count": stats["videos"]["file_count"],
            "frames_count": stats["frames"]["file_count"],
        }

        return result


# Singleton instance
screen_recording_storage = ScreenRecordingStorage()


def get_recording_path(
    session_id: str | None = None, timestamp: int | None = None, ext: str = "mp4"
) -> str:
    """Convenience function to get recording path."""
    return screen_recording_storage.get_recording_path(session_id, timestamp, ext)


def get_frame_path(session_id: str, timestamp_ms: int, ext: str = "png") -> str:
    """Convenience function to get frame path."""
    return screen_recording_storage.get_frame_path(session_id, timestamp_ms, ext)
