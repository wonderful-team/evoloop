"""
File-based lock adapter for FileCache.
"""

import asyncio
import logging
import os
import time
from pathlib import Path

from app.infrastructure.cache.abstract import CacheLock

logger = logging.getLogger(__name__)


try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt

    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False
    msvcrt = None  # type: ignore[assignment]


class FileCacheLockAdapter(CacheLock):
    def __init__(self, name: str):
        self.name = name
        self._locked = False
        self._fd: int | None = None
        self._lock_file: Path | None = None

    async def acquire(self, blocking: bool = True, blocking_timeout: float | None = None) -> bool:
        if self._locked:
            return True

        from app.core.config import settings

        lock_dir = Path(settings.APP_DATA_DIR) / "cache" / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        self._lock_file = lock_dir / f"{self.name}.lock"

        try:
            fd = os.open(str(self._lock_file), os.O_CREAT | os.O_RDWR)
            self._fd = fd

            if _HAS_FCNTL:
                return await self._acquire_fcntl(fd, blocking, blocking_timeout)
            elif _HAS_MSVCRT:
                return await self._acquire_msvcrt(fd, blocking, blocking_timeout)
            else:
                self._locked = True
                return True
        except OSError as e:
            logger.warning("[FileCacheLock] Failed to acquire lock %s: %s", self.name, e)
            return False

    async def _acquire_fcntl(self, fd: int, blocking: bool, blocking_timeout: float | None) -> bool:
        if blocking and blocking_timeout is None:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._locked = True
            return True

        if not blocking:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._locked = True
                return True
            except OSError:
                os.close(fd)
                self._fd = None
                return False

        deadline = time.monotonic() + blocking_timeout
        while time.monotonic() < deadline:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._locked = True
                return True
            except OSError:
                await asyncio.sleep(0.05)

        os.close(fd)
        self._fd = None
        return False

    async def _acquire_msvcrt(self, fd: int, blocking: bool, blocking_timeout: float | None) -> bool:
        import time

        if blocking and blocking_timeout is None:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            self._locked = True
            return True

        if not blocking:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                self._locked = True
                return True
            except OSError:
                os.close(fd)
                self._fd = None
                return False

        deadline = time.monotonic() + blocking_timeout
        while time.monotonic() < deadline:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                self._locked = True
                return True
            except OSError:
                await asyncio.sleep(0.05)

        os.close(fd)
        self._fd = None
        return False

    async def release(self) -> None:
        if not self._locked:
            return

        try:
            if self._fd is not None:
                if _HAS_FCNTL:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                elif _HAS_MSVCRT:
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                os.close(self._fd)
                self._fd = None
        except OSError as e:
            logger.warning("[FileCacheLock] Error releasing lock %s: %s", self.name, e)
        finally:
            self._locked = False

    def __del__(self):
        if self._locked and self._fd is not None:
            try:
                if _HAS_FCNTL:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                elif _HAS_MSVCRT:
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                os.close(self._fd)
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)
