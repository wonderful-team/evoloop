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

from app.domain.codebase.filter import FileFilter
from app.utils.detect import is_code_file

logger = logging.getLogger(__name__)


# --- Global Observer Manager ---


class GlobalObserverManager:
    """
    Singleton to manage a single Watchdog Observer instance for the entire application.
    This prevents resource exhaustion and conflict issues on macOS (FSEvents).
    """

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
                    logger.info("Global Watchdog Observer started.")
                except Exception as e:
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
                logger.debug(f"Scheduled watch on: {path}")
            except RuntimeError as re:
                if "already scheduled" in str(re):
                    logger.warning(f"Watch already scheduled for {path}. Skipping/Ignoring.")
                else:
                    raise re
            except Exception as e:
                logger.error(f"Failed to schedule watch for {path}: {e}")

    def unschedule(self, path: str):
        path = os.path.abspath(path)
        with self._lock:
            if path in self._watches:
                watch = self._watches[path]
                try:
                    self._observer.unschedule(watch)
                    del self._watches[path]
                    logger.debug(f"Unscheduled watch on: {path}")
                except Exception as e:
                    logger.error(f"Error unscheduling watch for {path}: {e}")


# Global instance
observer_manager = GlobalObserverManager()


# --- Reuse Handlers ---


class IndexingEventHandler(FileSystemEventHandler):
    """
    File system event handler that publishes to the unified event bus.
    
    Instead of directly calling IndexingService, this handler publishes
    events (FileModifiedEvent, FileRemovedEvent, FileMovedEvent) to the
    system event bus. FileIndexingHandler subscribes to these events
    and performs the actual indexing operations.
    """
    
    def __init__(self, repo_id: int, loop: asyncio.AbstractEventLoop):
        self.repo_id = repo_id
        self.loop = loop
        self._pending_tasks: dict[str, asyncio.TimerHandle] = {}
        self._debounce_delay = 2.0  # Seconds
        self.file_filter = FileFilter()

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
        # 1. Check if the file is a code file (extension/shebang)
        if not is_code_file(path):
            return False

        # 2. Check global exclusion rules (node_modules, .git, large files, etc.)
        return self.file_filter.should_include(path)

    def _process(self, path: str):
        if self._is_valid_code_file(path):
            # Debounce Logic
            if path in self._pending_tasks:
                self._pending_tasks[path].cancel()

            # Schedule new task
            # We schedule a callback on the LOOP, which will then launch the coroutine
            task = self.loop.call_later(
                self._debounce_delay,
                lambda: asyncio.create_task(self._debounce_callback(path)),
            )
            self._pending_tasks[path] = task

    async def _debounce_callback(self, path: str):
        """Publish FileModifiedEvent to the event bus."""
        # Cleanup
        self._pending_tasks.pop(path, None)

        logger.info(f"File modified (Debounced): {path}")
        
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
        event_handler = IndexingEventHandler(self.repo_id, loop)
        observer_manager.schedule(event_handler, self.path, recursive=True)

    def stop(self):
        observer_manager.unschedule(self.path)


class ProjectDiscoveryEventHandler(FileSystemEventHandler):
    """
    File system event handler that publishes project events to the unified event bus.
    
    Instead of directly calling ProjectSyncService, this handler publishes
    events (ProjectCreatedEvent, ProjectDeletedEvent, ProjectMovedEvent) to the
    system event bus. ProjectSyncHandler subscribes to these events
    and performs the actual synchronization operations.
    """
    
    def __init__(self, root_path: str, loop: asyncio.AbstractEventLoop):
        self.root_path = root_path
        self.loop = loop

    def on_created(self, event):
        if not event.is_directory:
            return
        # Only handle direct children of root_path
        parent = os.path.dirname(event.src_path)
        if os.path.normpath(parent) != os.path.normpath(self.root_path):
            return
        logger.info(f"Project Created (Detected): {event.src_path}")
        self._publish_project_created(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            return
        # src_path is the OLD path. If its parent was root_path, it's a rename or move-out.
        src_parent = os.path.dirname(event.src_path)
        dest_parent = os.path.dirname(event.dest_path)

        is_src_in_root = os.path.normpath(src_parent) == os.path.normpath(self.root_path)
        is_dest_in_root = os.path.normpath(dest_parent) == os.path.normpath(self.root_path)

        if is_src_in_root and is_dest_in_root:
            # Rename in-place
            logger.info(f"Project Renamed (Detected): {event.src_path} -> {event.dest_path}")
            self._publish_project_moved(event.src_path, event.dest_path)
        elif is_src_in_root and not is_dest_in_root:
            # Moved out of root -> Treat as deletion
            logger.info(f"Project Moved Out (Detected): {event.src_path} -> {event.dest_path}")
            self._publish_project_deleted(event.src_path)
        elif not is_src_in_root and is_dest_in_root:
            # Moved into root from elsewhere -> Treat as creation
            logger.info(f"Project Moved In (Detected): {event.src_path} -> {event.dest_path}")
            self._publish_project_created(event.dest_path)

    def on_deleted(self, event):
        if not event.is_directory:
            return
        # Only handle direct children of root_path
        parent = os.path.dirname(event.src_path)
        if os.path.normpath(parent) != os.path.normpath(self.root_path):
            return
        logger.info(f"Project Deleted (Detected): {event.src_path}")
        self._publish_project_deleted(event.src_path)

    def _publish_project_created(self, path: str):
        """Publish ProjectCreatedEvent to the event bus."""
        from app.domain.project.event.publishers import publish_project_created
        
        asyncio.run_coroutine_threadsafe(
            publish_project_created(path=path, repo_id=0, project_id=None, project_name=""),
            self.loop
        )

    def _publish_project_deleted(self, path: str):
        """Publish ProjectDeletedEvent to the event bus."""
        from app.domain.project.event.publishers import publish_project_deleted
        
        asyncio.run_coroutine_threadsafe(
            publish_project_deleted(path=path, repo_id=0, project_id=None),
            self.loop
        )

    def _publish_project_moved(self, src_path: str, dest_path: str):
        """Publish ProjectMovedEvent to the event bus."""
        from app.domain.project.event.publishers import publish_project_moved
        
        asyncio.run_coroutine_threadsafe(
            publish_project_moved(src_path=src_path, dest_path=dest_path),
            self.loop
        )


class ProjectDiscoveryWatcher:
    """
    Watches the WORKSPACE_ROOT using the global observer.
    """

    def __init__(self, root_path: str):
        self.root_path = root_path

    def start(self):
        if not os.path.exists(self.root_path):
            logger.warning(f"Root path {self.root_path} does not exist. Cannot watch for new projects.")
            return

        logger.info(f"Starting Project Discovery Watcher on: {self.root_path}")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # If explicit loop needed or not running (should be running in server)
            loop = asyncio.new_event_loop()

        event_handler = ProjectDiscoveryEventHandler(self.root_path, loop)
        observer_manager.schedule(event_handler, self.root_path, recursive=True)

    def stop(self):
        observer_manager.unschedule(self.root_path)
