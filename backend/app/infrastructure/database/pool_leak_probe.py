"""
Async pool connection-leak probe (debugging only).

Targets the recurring SQLAlchemy error "The garbage collector is trying to clean
up non-checked-in connection ..." from the EMBEDDED_MODE async engine
(AsyncAdaptedQueuePool). That message is produced by
``sqlalchemy.pool.base._finalize_fairy`` in its GC-cleanup path: an async
connection was checked out and never returned (see sqlalchemy/sqlalchemy#12710).

Because the checkout happens inside a greenlet, a normal ``traceback`` taken at
the pool ``checkout`` event shows only pool/greenlet internals. This module
instead rebuilds the requesting coroutine's async call chain from the running
asyncio task (walking ``cr_await`` over the suspended coroutine frames), so the
log shows the actual app-level borrower (e.g. ``session_scope`` frames in
``database.py``) instead of the meaningless GC-trigger site.

Enabled only when ``EVOLOOP_POOL_LEAK_PROBE=1``:
  - records the checkout chain per ``_ConnectionRecord``,
  - wraps ``sqlalchemy.pool.base._finalize_fairy`` to log that chain when GC
    abandons a non-checked-in async connection,
  - runs a periodic ``gc.collect()`` (``EVOLOOP_POOL_LEAK_PROBE_GC_INTERVAL``,
    default 5s) so orphaned connections surface deterministically.
"""

import asyncio
import functools
import gc
import logging
import os
import threading
import time
import traceback
import weakref
from typing import Any

import sqlalchemy.pool.base as pool_base
from sqlalchemy import event

logger = logging.getLogger("pool_leak_probe")

_ENABLED = os.environ.get("EVOLOOP_POOL_LEAK_PROBE") == "1"
_GC_INTERVAL = float(os.environ.get("EVOLOOP_POOL_LEAK_PROBE_GC_INTERVAL", "5") or 5)

_records: dict[int, str] = {}
_records_ts: dict[int, float] = {}  # record id -> checkout time (unix)
_linger_reported: set[int] = set()  # 已报过的 linger（一条滞留只报一次，防 5s 周期刷 16k 行）
_by_task: dict[int, set[int]] = {}  # task id -> set of record ids it checked out
_lock = threading.Lock()
_finalize_patched = False
_gc_tasks: set[asyncio.Task] = set()
# per-fairy 追踪：record 级 stack 会被后续 checkout 覆盖（StaticPool/队列池连接
# 复用场景抓不到真泄漏者）。以 fairy 为粒度登记 weakref + 借用栈，fairy 被 GC
# 时若仍未 checkin → 点名泄漏点。
_fairy_watch: dict[int, dict] = {}
_checkin_patched = False


def _on_fairy_gc(fairy_id: int, _ref: weakref.ref) -> None:
    entry = _fairy_watch.pop(fairy_id, None)
    if entry is None:
        return  # 正常 checkin 过
    logger.warning(
        "[PoolLeakProbe] FAIRY GC'd WITHOUT CHECKIN (LEAKED SESSION)\n%s",
        entry["stack"],
    )


def _patch_fairy_checkin() -> None:
    global _checkin_patched
    if _checkin_patched:
        return

    fairy_cls = pool_base._ConnectionFairy
    orig_checkin = fairy_cls._checkin

    def _traced_checkin(self, *args: Any, **kwargs: Any):
        _fairy_watch.pop(id(self), None)
        return orig_checkin(self, *args, **kwargs)

    fairy_cls._checkin = _traced_checkin
    _checkin_patched = True
_LINGER_THRESHOLD = float(
    os.environ.get("EVOLOOP_POOL_LEAK_PROBE_LINGER", "30") or 30
)


def _async_chain(task: asyncio.Task) -> list[str]:
    """Rebuild the awaiting coroutine chain of ``task`` via ``cr_await``.

    Each suspended coroutine frame is where that function invoked ``await``;
    walking ``cr_await`` from the task's top coroutine down to the leaf reveals
    the app-level borrower path (session scope / async session / async engine)
    even though the synchronous greenlet frames are not visible.
    """
    lines: list[str] = []
    get_coro = getattr(task, "get_coro", None)
    coro = get_coro() if get_coro is not None else None
    seen: set[int] = set()
    for _ in range(80):
        if coro is None:
            break
        ident = id(coro)
        if ident in seen:
            break
        seen.add(ident)
        frame = getattr(coro, "cr_frame", None)
        if frame is not None:
            lines.append(
                f"    {frame.f_code.co_name}()  {frame.f_code.co_filename}:{frame.f_lineno}"
            )
        coro = getattr(coro, "cr_await", None)
    return lines


def _capture_checkout() -> str:
    task = asyncio.current_task()
    header = f"task={task.get_name()!r}" if task is not None else "task=None(no running loop)"
    parts = [f"checkout stack of {header}"]
    if task is not None:
        chain = _async_chain(task)
        if chain:
            parts.append("async chain (innermost first):")
            parts.extend(chain)
        else:
            parts.append("async chain: (empty)")
    parts.append("--- sync/greenlet frames ---")
    sync_frames = traceback.format_stack(limit=64)
    trimmed = sync_frames[:-2] if len(sync_frames) > 2 else sync_frames
    parts.extend(line.rstrip() for line in trimmed)
    return "\n".join(parts)


def _capture_task_state(task: asyncio.Task) -> str:
    """Capture where a task is currently suspended (its await point).

    Used when a task ends abnormally (cancelled) while still holding
    checked-out pool records, to reveal the exact await that the task was
    suspended at when it was cancelled.
    """
    parts = [
        f"task={task.get_name()!r} state={task._state} "
        f"cancelling={getattr(task, '_must_cancel', 0)}"
    ]
    if task.cancelled():
        parts.append("reason: task.cancelled()")
    exc = task.exception() if task.done() and not task.cancelled() else None
    if exc is not None:
        parts.append(f"exception: {exc!r}")
    stack = task.get_stack(limit=20)
    if stack:
        parts.append("--- task stack at end (innermost first) ---")
        for fr in stack:
            parts.append(
                f"    {fr.f_code.co_name}()  {fr.f_code.co_filename}:{fr.f_lineno}"
            )
    coro = task.get_coro() if callable(getattr(task, "get_coro", None)) is not None else None
    if coro is None:
        coro = None
    parts.append("--- async chain ---")
    if coro is not None:
        chain = _async_chain(task)
        parts.extend(chain or ["    (empty)"])
    else:
        parts.append("    (coroutine already consumed)")
    return "\n".join(parts)


def _on_task_done(task: asyncio.Task) -> None:
    """When a task finishes (esp. cancelled), report still-outstanding records."""
    if not task.done():
        return
    task_id = id(task)
    with _lock:
        rec_ids = _by_task.pop(task_id, set())
        pending = [
            key for key in rec_ids if key in _records
        ]
    if not pending:
        return
    state = _capture_task_state(task)
    logger.warning(
        "[PoolLeakProbe] Task ENDED while still holding %d checked-out record(s):\n%s",
        len(pending),
        state,
    )


def _on_checkout(  # noqa: ARG001 - arg names must match PoolEvents.checkout dispatch
    dbapi_connection, connection_record, connection_proxy  # noqa: ARG001
) -> None:
    stack = _capture_checkout()
    task = asyncio.current_task()
    task_id = id(task) if task is not None else None
    key = id(connection_record)
    now = time.time()
    with _lock:
        _records[key] = stack
        _records_ts[key] = now
        if task_id is not None:
            conn_ids = _by_task.setdefault(task_id, set())
            first_for_task = not conn_ids
            conn_ids.add(key)
            if first_for_task and task is not None:
                try:
                    task.add_done_callback(_on_task_done)
                except (RuntimeError, AssertionError):
                    pass
        try:
            connection_record.info["pool_leak_probe_stack"] = stack
        except Exception:
            pass


def _on_checkin(  # noqa: ARG001 - arg names must match PoolEvents.checkin dispatch
    dbapi_connection, connection_record  # noqa: ARG001
) -> None:
    """Record a proper checkin so abandoned-but-returned is not misreported."""
    with _lock:
        key = id(connection_record)
        _records.pop(key, None)
        _records_ts.pop(key, None)
        # 归因必须同步清理：record 对象被池复用，若旧借用人不清除，
        # 其 task 结束时会把"他人正在持有的同一 record"误报为泄漏（实测
        # Task-1xx FINISHED holding 3 全属此类假阳性）。
        for conn_ids in _by_task.values():
            conn_ids.discard(key)
        _linger_reported.discard(key)


def _sweep_lingers() -> None:
    """Report checkouts that have been outstanding (unchecked-in) too long.

    This is the *live* sweep that the GC-abandon and task-done hooks cannot
    provide: those two fire only after a fairy has already been abandoned
    (GC) or its borrower already ended. Here we catch the *still-alive*
    borrower that checked a connection out and simply never returned it while
    remaining suspended — the exact 16:22:51 scenario (alive task holding a
    fully-formed fairy with no GC trigger yet).
    """
    now = time.time()
    with _lock:
        stale = [
            key
            for key, checked_out_at in _records_ts.items()
            if checked_out_at and (now - checked_out_at) >= _LINGER_THRESHOLD
        ]
        borrower_for: dict[int, str] = {}
        for task_id, ids in _by_task.items():
            for key in ids:
                if key in stale:
                    borrower_for.setdefault(key, str(task_id))
        states: dict[int, str] = {}
        for key in stale:
            states[key] = _records.get(key, "(checkout stack missing)")
    for key in stale:
        if key in _linger_reported:
            continue
        _linger_reported.add(key)
        logger.warning(
            "[PoolLeakProbe] async connection still checked out after "
            "%.0fs (linger threshold %.0fs):\n"
            "record %d, holder task id=%s\n"
            "BORROWED VIA:\n%s",
            now - _records_ts[key],
            _LINGER_THRESHOLD,
            key,
            borrower_for.get(key, "unknown"),
            states.get(key, "(stack missing)"),
        )


def _patched_finalize_fairy(
    dbapi_connection,
    connection_record,
    pool,
    ref,
    echo,
    transaction_was_reset=False,
    fairy=None,
):
    if ref is not None and connection_record is not None:
        dialect = getattr(pool, "_dialect", None)
        is_async = bool(dialect) and bool(getattr(dialect, "is_async", False))
        if is_async:
            key = id(connection_record)
            with _lock:
                checkout = _records.pop(key, None)
                for conn_ids in _by_task.values():
                    conn_ids.discard(key)
            if checkout is None:
                try:
                    checkout = connection_record.info.get(
                        "pool_leak_probe_stack"
                    )
                except Exception:
                    checkout = None
            gc_stack = "".join(traceback.format_stack(limit=6))
            logger.warning(
                "[PoolLeakProbe] GC is abandoning async connection %r "
                "(record %r, object %d)\n"
                "BORROWED VIA:\n%s\n"
                "GC TRIGGER SITE:\n%s",
                getattr(connection_record, "dbapi_connection", None),
                connection_record,
                key,
                checkout or "(checkout stack not captured)",
                gc_stack,
            )
    return pool_base._orig_finalize_fairy(
        dbapi_connection,
        connection_record,
        pool,
        ref,
        echo,
        transaction_was_reset=transaction_was_reset,
        fairy=fairy,
    )


def maybe_install(engine) -> None:
    """Install the probe on an async engine's pool. No-op unless enabled."""
    if not _ENABLED:
        return

    event.listen(engine.pool, "checkout", _on_checkout)
    event.listen(engine.pool, "checkin", _on_checkin)

    global _finalize_patched
    if not _finalize_patched:
        pool_base._orig_finalize_fairy = pool_base._finalize_fairy
        pool_base._finalize_fairy = _patched_finalize_fairy
        _finalize_patched = True

    logger.info(
        "[PoolLeakProbe] installed on async pool %r (gc_interval=%ss)",
        engine.pool,
        _GC_INTERVAL,
    )
    _start_periodic_gc()


def _start_periodic_gc() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _gc_loop() -> None:
        while True:
            try:
                await asyncio.sleep(_GC_INTERVAL)
                collected = gc.collect()
                if collected:
                    logger.debug(
                        "[PoolLeakProbe] periodic gc.collect() freed %d objects",
                        collected,
                    )
                _sweep_lingers()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("[PoolLeakProbe] periodic gc task error")

    task = asyncio.create_task(_gc_loop())
    _gc_tasks.add(task)
    task.add_done_callback(_gc_tasks.discard)


def _watch_fairy(fairy: Any, record_id: int, stack: str) -> None:
    _patch_fairy_checkin()
    fid = id(fairy)
    stale = _fairy_watch.pop(fid, None)
    if stale is not None:
        stale["ref"] = None
    try:
        ref = weakref.ref(fairy, functools.partial(_on_fairy_gc, fid))
    except TypeError:
        return
    _fairy_watch[fid] = {"ref": ref, "record": record_id, "stack": stack}
