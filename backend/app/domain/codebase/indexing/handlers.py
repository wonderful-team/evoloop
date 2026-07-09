"""
DebouncedIndexHandler: Batched, debounced file indexing from file system events.

Performance design:
  - All indexing work is offloaded to the Huey/Celery worker thread via
    ``index_file_task.delay()`` etc., so the main event loop is never blocked
    by TreeSitter parsing, embedding generation, or database I/O.
  - Per-repo timers prevent one repo's events from resetting another's debounce.
  - A global ``_processing`` flag prevents concurrent batch execution.
  - Individual file tasks have built-in timeouts.
"""

import asyncio
import logging

from app.core.events.decorators import event_register, event_subscribe
from app.domain.codebase.event.schemas import (
    FileModifiedEvent,
    FileMovedEvent,
    FileRemovedEvent,
)
from app.domain.codebase.event.types import IndexingEventType

logger = logging.getLogger(__name__)


@event_register()
class DebouncedIndexHandler:
    """
    Subscribes to file change events and batches them together.

    Instead of indexing each file immediately, this handler:
    1. Accumulates all pending changes per repo
    2. Resets a per-repo debounce timer on each new event
    3. When a repo's timer fires (no new events for BATCH_DEBOUNCE seconds),
       the accumulated changes are dispatched as background tasks.

    This prevents thrashing during active editing (e.g., IDE auto-save,
    git checkout, branch switch) where many files change rapidly.
    """

    BATCH_DEBOUNCE: float = 180.0
    """Seconds of inactivity before accumulated changes are dispatched."""

    PER_FILE_TIMEOUT: float = 120.0
    """Max seconds a single index_file task may run before being abandoned."""

    def __init__(self):
        self._pending_modified: dict[int, set[str]] = {}
        self._pending_removed: dict[int, set[str]] = {}
        self._pending_moved: dict[int, list[tuple[str, str]]] = {}
        self._batch_timers: dict[int, asyncio.TimerHandle] = {}
        self._processing: bool = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Event Subscribers
    # ------------------------------------------------------------------

    @event_subscribe(IndexingEventType.FILE_MODIFIED)
    async def on_file_modified(self, event: FileModifiedEvent) -> None:
        repo_id = event.repo_id
        file_path = event.file_path

        async with self._lock:
            self._pending_modified.setdefault(repo_id, set()).add(file_path)
            self._pending_removed.get(repo_id, set()).discard(file_path)

        self._schedule_batch(repo_id)

    @event_subscribe(IndexingEventType.FILE_REMOVED)
    async def on_file_removed(self, event: FileRemovedEvent) -> None:
        repo_id = event.repo_id
        file_path = event.file_path

        async with self._lock:
            self._pending_removed.setdefault(repo_id, set()).add(file_path)
            self._pending_modified.get(repo_id, set()).discard(file_path)

        self._schedule_batch(repo_id)

    @event_subscribe(IndexingEventType.FILE_MOVED)
    async def on_file_moved(self, event: FileMovedEvent) -> None:
        repo_id = event.repo_id

        async with self._lock:
            self._pending_moved.setdefault(repo_id, []).append(
                (event.src_path, event.dest_path)
            )
            self._pending_removed.get(repo_id, set()).discard(event.src_path)
            self._pending_modified.get(repo_id, set()).discard(event.src_path)

        self._schedule_batch(repo_id)

    # ------------------------------------------------------------------
    # Per-repo batch debounce
    # ------------------------------------------------------------------

    def _schedule_batch(self, repo_id: int, debounce: float | None = None) -> None:
        timer = self._batch_timers.get(repo_id)
        if timer is not None:
            timer.cancel()

        delay = debounce if debounce is not None else self.BATCH_DEBOUNCE
        loop = asyncio.get_running_loop()
        self._batch_timers[repo_id] = loop.call_later(
            delay,
            lambda rid=repo_id: asyncio.create_task(self._process_batch(rid)),
        )

    # ------------------------------------------------------------------
    # Batch processing — dispatched to worker thread
    # ------------------------------------------------------------------

    async def _process_batch(self, repo_id: int) -> None:
        self._batch_timers.pop(repo_id, None)

        async with self._lock:
            if self._processing:
                logger.debug(f"[DebouncedIndex] Skipping batch for repo {repo_id} — already processing")
                return
            self._processing = True

            modified = self._pending_modified.pop(repo_id, set())
            removed = self._pending_removed.pop(repo_id, set())
            moved = self._pending_moved.pop(repo_id, list())

        file_count = len(modified) + len(removed) + len(moved)
        if file_count == 0:
            self._processing = False
            return

        logger.info(
            f"[DebouncedIndex] Dispatching batch for repo {repo_id}: "
            f"{len(modified)} modified, {len(removed)} removed, {len(moved)} moved"
        )

        from app.domain.codebase.indexing.tasks import (
            index_file_task,
            move_file_task,
            remove_file_task,
        )

        try:
            for file_path in removed:
                remove_file_task.delay(file_path, repo_id)

            for src, dest in moved:
                move_file_task.delay(src, dest, repo_id)

            # Chunked dispatch: 10 files per batch, 1s between batches,
            # at most 20 files per cycle.  Leftovers are retried after 5s.
            modified_list = sorted(modified)
            MAX_PER_CYCLE = 20
            BATCH_SIZE = 10
            BATCH_INTERVAL = 1.0

            to_dispatch = modified_list[:MAX_PER_CYCLE]
            leftover = modified_list[MAX_PER_CYCLE:]

            for i in range(0, len(to_dispatch), BATCH_SIZE):
                chunk = to_dispatch[i:i + BATCH_SIZE]
                for file_path in chunk:
                    index_file_task.delay(file_path, repo_id)
                if i + BATCH_SIZE < len(to_dispatch):
                    await asyncio.sleep(BATCH_INTERVAL)

            if leftover:
                self._pending_modified.setdefault(repo_id, set()).update(leftover)
                self._schedule_batch(repo_id, debounce=5.0)
        finally:
            self._processing = False
