"""
Core file watcher with Event System integration.

This module provides file watching capabilities that integrate with the
core event system (app.core.events). File changes are published as events
to the system_bus, allowing decoupled handling by any subscriber.

Usage:
    # Method 1: Direct event subscription
    from app.core.events import system_bus
    from app.core.file.events import FileSystemEventType
    
    async def on_file_changed(event):
        if event.event_type == FileSystemEventType.FILE_MODIFIED:
            print(f"File modified: {event.data['path']}")
    
    system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, on_file_changed)
    
    # Method 2: Use FileWatcher (publishes to event bus)
    from app.core.file.watcher import FileWatcher
    
    watcher = FileWatcher("/workspace")
    watcher.start()

Events Published:
    - FileSystemEventType.FILE_CREATED
    - FileSystemEventType.FILE_MODIFIED
    - FileSystemEventType.FILE_DELETED
    - FileSystemEventType.FILE_MOVED
    - FileSystemEventType.DIRECTORY_CREATED
    - FileSystemEventType.DIRECTORY_DELETED
    - FileSystemEventType.WATCHER_STARTED
    - FileSystemEventType.WATCHER_STOPPED
"""

import asyncio
import logging
import os
import threading
from typing import Any, Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.core.events import system_bus
from app.core.file.events import FileSystemEventType, FileWatcherEvent

logger = logging.getLogger(__name__)


class _EventBusHandler(FileSystemEventHandler):
    """
    Internal handler that publishes watchdog events to the system event bus.
    
    This handler is thread-safe and can be called from watchdog's observer thread.
    """
    
    def __init__(
        self,
        watch_path: str,
        file_filter: Optional[Callable[[str], bool]] = None,
        debounce_delay: float = 0.0,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.watch_path = watch_path
        self.file_filter = file_filter
        self.debounce_delay = debounce_delay
        self._event_loop = event_loop
        self._pending_tasks: dict[str, Any] = {}
        self._lock = threading.Lock()
    
    def _should_process(self, path: str) -> bool:
        """Check if path should be processed."""
        if self.file_filter is None:
            return True
        return self.file_filter(path)
    
    def _publish_event(self, event_type: FileSystemEventType, path: str, **extra_data):
        """Publish event to system bus from any thread."""
        event = FileWatcherEvent(
            event_type=event_type,
            data={
                "path": path,
                "watch_path": self.watch_path,
                **extra_data
            }
        )
        
        # Use the stored event loop to publish from main thread
        if self._event_loop and self._event_loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    system_bus.publish(event),
                    self._event_loop
                )
            except Exception as e:
                logger.error(f"Failed to schedule event publish: {e}")
        else:
            logger.debug(f"Event loop not available, skipping event: {event_type}")
    
    def _schedule_publish(self, event_type: FileSystemEventType, path: str, **extra_data):
        """Schedule event publish with optional debouncing."""
        if self.debounce_delay > 0:
            with self._lock:
                # Cancel pending task for this path
                if path in self._pending_tasks:
                    self._pending_tasks[path].cancel()
                
                # Schedule new task using the event loop
                if self._event_loop and self._event_loop.is_running():
                    try:
                        task = self._event_loop.call_later(
                            self.debounce_delay,
                            lambda: self._publish_event(event_type, path, **extra_data)
                        )
                        self._pending_tasks[path] = task
                    except Exception as e:
                        logger.error(f"Failed to schedule debounced publish: {e}")
                        # Fallback to immediate publish
                        self._publish_event(event_type, path, **extra_data)
                else:
                    # No event loop, publish immediately
                    self._publish_event(event_type, path, **extra_data)
        else:
            self._publish_event(event_type, path, **extra_data)
    
    def on_created(self, event: FileSystemEvent):
        path = event.src_path
        if not self._should_process(path):
            return
        
        if event.is_directory:
            self._publish_event(FileSystemEventType.DIRECTORY_CREATED, path)
        else:
            self._publish_event(FileSystemEventType.FILE_CREATED, path)
    
    def on_modified(self, event: FileSystemEvent):
        path = event.src_path
        if not self._should_process(path):
            return
        
        if not event.is_directory:
            self._schedule_publish(FileSystemEventType.FILE_MODIFIED, path)
    
    def on_deleted(self, event: FileSystemEvent):
        path = event.src_path
        if not self._should_process(path):
            return
        
        if event.is_directory:
            self._publish_event(FileSystemEventType.DIRECTORY_DELETED, path)
        else:
            self._publish_event(FileSystemEventType.FILE_DELETED, path)
    
    def on_moved(self, event: FileSystemEvent):
        src_path = event.src_path
        dest_path = event.dest_path
        
        if not self._should_process(src_path) and not self._should_process(dest_path):
            return
        
        self._publish_event(
            FileSystemEventType.FILE_MOVED,
            src_path,
            dest_path=dest_path,
            is_directory=event.is_directory
        )


class FileWatcher:
    """
    File system watcher that publishes events to the system event bus.
    
    This class integrates with app.core.events system, making it easy
    for any module to subscribe to file system changes without direct
    dependencies on the file watcher.
    
    Example:
        # Start watching
        watcher = FileWatcher("/workspace", debounce_delay=1.0)
        watcher.start()
        
        # Subscribe to events elsewhere
        from app.core.events import system_bus
        from app.core.file.events import FileSystemEventType
        
        async def on_change(event):
            print(f"File changed: {event.data['path']}")
        
        system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, on_change)
    """
    
    def __init__(
        self,
        path: str,
        *,
        recursive: bool = True,
        debounce_delay: float = 0.0,
        file_filter: Optional[Callable[[str], bool]] = None,
    ):
        """
        Initialize file watcher.
        
        Args:
            path: Directory or file to watch
            recursive: Watch subdirectories
            debounce_delay: Delay in seconds before triggering event (0 = no debounce)
            file_filter: Optional function to filter paths
        """
        self.path = os.path.abspath(path)
        self.recursive = recursive
        self.debounce_delay = debounce_delay
        self.file_filter = file_filter
        
        self._observer: Optional[Observer] = None
        self._handler: Optional[_EventBusHandler] = None
        self._watch = None
        self._started = False
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
    
    def start(self) -> "FileWatcher":
        """Start watching and publish FILE_WATCHER_STARTED event."""
        if self._started:
            logger.warning(f"Watcher already started for {self.path}")
            return self
        
        try:
            # Store the current event loop for cross-thread communication
            try:
                self._event_loop = asyncio.get_running_loop()
            except RuntimeError:
                self._event_loop = None
                logger.warning("No running event loop, events will not be published")
            
            self._observer = Observer()
            self._handler = _EventBusHandler(
                watch_path=self.path,
                file_filter=self.file_filter,
                debounce_delay=self.debounce_delay,
                event_loop=self._event_loop,
            )
            self._watch = self._observer.schedule(
                self._handler,
                self.path,
                recursive=self.recursive
            )
            self._observer.start()
            self._started = True
            
            # Publish started event
            if self._event_loop and self._event_loop.is_running():
                event = FileWatcherEvent(
                    event_type=FileSystemEventType.WATCHER_STARTED,
                    data={"path": self.path, "recursive": self.recursive}
                )
                asyncio.create_task(system_bus.publish(event))
            
            logger.info(f"Started file watcher: {self.path}")
            
        except Exception as e:
            logger.error(f"Failed to start watcher for {self.path}: {e}")
            self._cleanup()
            raise
        
        return self
    
    def stop(self):
        """Stop watching and publish FILE_WATCHER_STOPPED event."""
        if not self._started:
            return
        
        self._cleanup()
        self._started = False
        
        # Publish stopped event
        try:
            if self._event_loop and self._event_loop.is_running():
                event = FileWatcherEvent(
                    event_type=FileSystemEventType.WATCHER_STOPPED,
                    data={"path": self.path}
                )
                asyncio.create_task(system_bus.publish(event))
        except Exception as e:
            logger.error(f"Failed to publish watcher stopped event: {e}")
        
        logger.info(f"Stopped file watcher: {self.path}")
    
    def _cleanup(self):
        """Clean up resources."""
        if self._observer:
            try:
                if self._watch:
                    self._observer.unschedule(self._watch)
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception as e:
                logger.error(f"Error cleaning up watcher: {e}")
            finally:
                self._observer = None
                self._handler = None
                self._watch = None
                self._event_loop = None
    
    def __enter__(self) -> "FileWatcher":
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    
    @property
    def is_running(self) -> bool:
        return self._started and self._observer is not None


class FileWatcherManager:
    """
    Manager for multiple file watchers.
    
    Provides centralized management of file watchers with automatic cleanup.
    All watchers publish to the system event bus.
    
    Example:
        manager = FileWatcherManager()
        
        # Watch multiple directories
        manager.create_watcher("/project1", debounce_delay=1.0)
        manager.create_watcher("/project2", debounce_delay=1.0)
        
        # Subscribe to all events
        from app.core.events import system_bus
        from app.core.file.events import FileSystemEventType
        system_bus.subscribe(FileSystemEventType.FILE_MODIFIED, on_any_file_change)
    """
    
    def __init__(self):
        self._watchers: dict[str, FileWatcher] = {}
    
    def create_watcher(
        self,
        path: str,
        *,
        recursive: bool = True,
        debounce_delay: float = 0.0,
        file_filter: Optional[Callable[[str], bool]] = None,
    ) -> FileWatcher:
        """
        Create and start a new watcher.
        
        Args:
            path: Path to watch
            recursive: Watch subdirectories
            debounce_delay: Debounce delay in seconds
            file_filter: File filter function
            
        Returns:
            Started FileWatcher instance
        """
        abs_path = os.path.abspath(path)
        
        # Stop existing watcher for this path
        if abs_path in self._watchers:
            self._watchers[abs_path].stop()
            del self._watchers[abs_path]
        
        # Create and start new watcher
        watcher = FileWatcher(
            path=abs_path,
            recursive=recursive,
            debounce_delay=debounce_delay,
            file_filter=file_filter,
        )
        watcher.start()
        
        self._watchers[abs_path] = watcher
        return watcher
    
    def stop_watcher(self, path: str):
        """Stop watcher for specific path."""
        abs_path = os.path.abspath(path)
        if abs_path in self._watchers:
            self._watchers[abs_path].stop()
            del self._watchers[abs_path]
    
    def stop_all(self):
        """Stop all watchers."""
        for watcher in self._watchers.values():
            watcher.stop()
        self._watchers.clear()
    
    def get_watcher(self, path: str) -> Optional[FileWatcher]:
        """Get watcher for specific path."""
        return self._watchers.get(os.path.abspath(path))
    
    @property
    def watcher_count(self) -> int:
        """Number of active watchers."""
        return len(self._watchers)
    
    def __enter__(self) -> "FileWatcherManager":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_all()
