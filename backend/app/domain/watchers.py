"""
File System Watchers with Event System Integration

This module provides file watching capabilities that publish events
to the unified event system (app.core.events), enabling decoupled
handling by FileIndexingHandler.
"""

import asyncio
import logging
import os
from threading import RLock
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.core.file import is_code_file
from app.core.file.filter import is_ignored_path
from app.domain.codebase.filter import FileFilter
from app.domain.codebase.ignore import NestedGitignoreMatcher

logger = logging.getLogger(__name__)


# --- Global Observer Manager ---

class GlobalObserverManager:
    """
    Singleton to manage a single Watchdog Observer instance for the entire application.
    This prevents resource exhaustion and conflict issues on macOS (FSEvents).
    """

    _started = False
    _instance = None
    _lock = RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self._observer = Observer()
        self._watches: dict[str, Any] = {}  # Map path -> Watch Object
        self._started = False

    def start_observer(self):
        with self._lock:
            if not self._started:
                try:
                    self._observer.start()
                    self._started = True
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"Failed to start Global Observer: {e}")

    def stop_observer(self):
        with self._lock:
            if self._started:
                self._observer.stop()
                self._observer.join()
                self._started = False
                logger.info("Global Watchdog Observer stopped.")

    def schedule(self, event_handler, path: str, recursive: bool = True):
        # Normalize path
        path = os.path.abspath(path)

        with self._lock:
            if not self._started:
                self.start_observer()

            # Check if this precise path is already watched
            # Note: Watchdog allows multiple handlers on the same path, but we might want to avoid duplicates if intended.
            # However, the user error "already scheduled" usually means Exact Same Watch (same handler instance or internal eq).
            # For simplicity, we just try to schedule and catch the error, or check our map.

            # If we already track this path, we might need to unschedule first if we want to replace,
            # or just add another handler (if watchdog supports it).
            # But the error "already scheduled" suggests strictness.

            try:
                # Schedule via watchdog
                watch = self._observer.schedule(event_handler, path, recursive=recursive)
                self._watches[path] = watch
            except RuntimeError as re:
                if "already scheduled" in str(re):
                    logger.warning(f"Watch already scheduled for {path}. Skipping/Ignoring.")
                else:
                    raise re
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"Failed to schedule watch for {path}: {e}")

    def unschedule(self, path: str):
        path = os.path.abspath(path)
        with self._lock:
            if path in self._watches:
                watch = self._watches[path]
                try:
                    self._observer.unschedule(watch)
                    del self._watches[path]
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"Error unscheduling watch for {path}: {e}")


# Global instance
observer_manager = GlobalObserverManager()


# --- Reuse Handlers ---

class IndexingEventSubscriber(FileSystemEventHandler):
    """
    File system event handler that publishes to the unified event bus.

    Instead of directly calling IndexingService, this handler publishes
    events (FileModifiedEvent, FileRemovedEvent, FileMovedEvent) to the
    system event bus. FileIndexingHandler subscribes to these events
    and performs the actual indexing operations.
    """

    def __init__(self, repo_id: int, loop: asyncio.AbstractEventLoop, repo_path: str | None = None):
        self.repo_id = repo_id
        self.loop = loop
        self._repo_path = repo_path
        self._pending_tasks: dict[str, asyncio.TimerHandle] = {}
        self._debounce_delay = 2.0  # Seconds
        self.file_filter = FileFilter()
        self._gitignore_matcher: NestedGitignoreMatcher | None = None
        if repo_path:
            self._gitignore_matcher = NestedGitignoreMatcher(repo_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        self._process(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        self._process(event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            return
        self._process_delete(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        self._process_move(event.src_path, event.dest_path)

    def _is_valid_code_file(self, path: str) -> bool:
        # 1. Check if the file is a code file (extension/shebang) - Fast check
        if not is_code_file(path):
            return False

        # 2. Check global exclusion rules (node_modules, .git, etc.) - Fast path check
        if is_ignored_path(path):
            return False

        # 3. Check .gitignore rules (if a matcher is available)
        if self._gitignore_matcher and self._gitignore_matcher.should_ignore(path, is_dir=False):
            return False

        return True

    def _process(self, path: str):
        if self._is_valid_code_file(path):
            # Debounce Logic
            if path in self._pending_tasks:
                self._pending_tasks[path].cancel()

            # Schedule new task
            task = self.loop.call_later(
                self._debounce_delay,
                lambda: asyncio.create_task(self._debounce_callback(path)),
            )
            self._pending_tasks[path] = task

    async def _debounce_callback(self, path: str):
        """Publish FileModifiedEvent to the event bus after verifying content filter."""
        # Cleanup
        self._pending_tasks.pop(path, None)

        # Run the heavy content-based FileFilter check only after debounce (avoids blocking watcher thread)
        if not self.file_filter.should_include(path):
            return

        logger.info(f"File modified (Debounced & Filtered): {path}")

        # Publish event to system bus instead of directly calling service
        from app.domain.codebase.event.publishers import publish_file_modified

        await publish_file_modified(repo_id=self.repo_id, file_path=path)

    def _process_delete(self, path: str):
        """Publish FileRemovedEvent to the event bus."""
        if self._is_valid_code_file(path):
            logger.info(f"File deleted: {path}")

            # Publish event to system bus instead of directly calling service
            from app.domain.codebase.event.publishers import publish_file_removed

            asyncio.run_coroutine_threadsafe(
                publish_file_removed(repo_id=self.repo_id, file_path=path),
                self.loop
            )

    def _process_move(self, src: str, dest: str):
        """Publish FileMovedEvent or FileRemovedEvent to the event bus."""
        src_valid = self._is_valid_code_file(src)
        dest_valid = self._is_valid_code_file(dest)

        if src_valid and dest_valid:
            logger.info(f"File moved: {src} -> {dest}")

            # Publish event to system bus instead of directly calling service
            from app.domain.codebase.event.publishers import publish_file_moved

            asyncio.run_coroutine_threadsafe(
                publish_file_moved(repo_id=self.repo_id, src_path=src, dest_path=dest),
                self.loop
            )
        elif src_valid and not dest_valid:
            # Moved out of valid scope -> Treat as delete
            self._process_delete(src)
        elif not src_valid and dest_valid:
            # Moved into valid scope -> Treat as create
            self._process(dest)


class RepoWatcher:
    """
    Watches a single repository directory using the global observer.

    File changes are published as events to the system event bus,
    where FileIndexingHandler subscribes and performs indexing.
    """

    def __init__(self, path: str, repo_id: int):
        self.path = path
        self.repo_id = repo_id

    def start(self):
        logger.info(f"Starting RepoWatcher on {self.path} (Repo ID: {self.repo_id})")
        loop = asyncio.get_running_loop()
        event_handler = IndexingEventSubscriber(self.repo_id, loop, repo_path=self.path)
        observer_manager.schedule(event_handler, self.path, recursive=True)

    def stop(self):
        observer_manager.unschedule(self.path)
