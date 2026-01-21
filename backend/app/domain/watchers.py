import asyncio
import logging
import os
from threading import RLock
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.domain.codebase.indexing.service import IndexingService
from app.domain.project.sync_service import project_sync_service
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
    def __init__(self, service: IndexingService, repo_id: int, loop: asyncio.AbstractEventLoop):
        self.service = service
        self.repo_id = repo_id
        self.loop = loop
        self._pending_tasks: dict[str, asyncio.TimerHandle] = {}
        self._debounce_delay = 2.0  # Seconds

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
        return is_code_file(path)

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
        # Cleanup
        self._pending_tasks.pop(path, None)

        logger.info(f"File modified (Debounced): {path}")
        await self.service.index_file(path, self.repo_id)

    def _process_delete(self, path: str):
        if self._is_valid_code_file(path):
            logger.info(f"File deleted: {path}")
            asyncio.run_coroutine_threadsafe(
                self.service.remove_file(path, self.repo_id),
                self.loop
            )

    def _process_move(self, src: str, dest: str):
        src_valid = self._is_valid_code_file(src)
        dest_valid = self._is_valid_code_file(dest)

        if src_valid and dest_valid:
            logger.info(f"File moved: {src} -> {dest}")
            asyncio.run_coroutine_threadsafe(
                self.service.move_file(src, dest, self.repo_id),
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
    """

    def __init__(self, path: str, repo_id: int):
        self.path = path
        self.repo_id = repo_id
        self.service = IndexingService()

    def start(self):
        logger.info(f"Starting RepoWatcher on {self.path} (Repo ID: {self.repo_id})")
        loop = asyncio.get_running_loop()
        event_handler = IndexingEventHandler(self.service, self.repo_id, loop)
        observer_manager.schedule(event_handler, self.path, recursive=True)

    def stop(self):
        observer_manager.unschedule(self.path)


class ProjectDiscoveryEventHandler(FileSystemEventHandler):
    def __init__(self, root_path: str, loop: asyncio.AbstractEventLoop):
        self.root_path = root_path
        self.loop = loop

    def on_created(self, event):
        if not event.is_directory:
            return
        parent = os.path.dirname(event.src_path)
        if os.path.abspath(parent) != os.path.abspath(self.root_path):
            return
        logger.info(f"Project Created (Detected): {event.src_path}")

    def on_moved(self, event):
        if not event.is_directory:
            return
        parent = os.path.dirname(event.src_path)
        if os.path.abspath(parent) != os.path.abspath(self.root_path):
            return
        # Ensure dest is also in root (rename)
        dest_parent = os.path.dirname(event.dest_path)
        if os.path.abspath(dest_parent) != os.path.abspath(self.root_path):
            return

        logger.info(f"Project Moved/Renamed (Detected): {event.src_path} -> {event.dest_path}")
        self._schedule_async(self._handle_project_moved(event.src_path, event.dest_path))

    def _schedule_async(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def _handle_project_created(self, project_path: str):
        try:
            await project_sync_service.handle_project_created(project_path)
        except Exception as e:
            logger.error(f"Error handling new project {project_path}: {e}")

    async def _handle_project_deleted(self, project_path: str):
        try:
            await project_sync_service.handle_project_deleted(project_path)
        except Exception as e:
            logger.error(f"Error handling deleted project {project_path}: {e}")

    async def _handle_project_moved(self, src_path: str, dest_path: str):
        try:
            await project_sync_service.handle_project_moved(src_path, dest_path)
        except Exception as e:
            logger.error(f"Error handling moved project {src_path}: {e}")


class ProjectDiscoveryWatcher:
    """
    Watches the PROJECTS_ROOT using the global observer.
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
