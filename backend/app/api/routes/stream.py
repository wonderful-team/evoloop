"""
SSE (Server-Sent Events) streaming endpoint for real-time chat updates.
Streams tokens and activity updates as they happen.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUserOptional, verify_guest_access
from app.core.config import settings
from app.core.engine.message.broker import event_replay_buffer, get_message_broker
from app.core.identity import identity_service
from app.core.monitoring.activity import activity_monitor
from app.domain.tasks.workflows import WorkflowError, WorkflowService
from app.infrastructure.database.sql.database import session_scope
from app.models import User
from app.models.codebase import Repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])


def _parse_last_event_seq(request: Request) -> int:
    """Parse SSE Last-Event-ID from header (browser auto-reconnect) or query param (manual reconnect)."""
    leid = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
    if leid and leid.isdigit():
        return int(leid)
    return 0


async def _replay_buffered(
    channel_id: str,
    floor_seq: int,
    baseline_seq: int,
    label: str,
) -> AsyncIterator[str]:
    """Yield buffered events in (floor_seq, baseline_seq] for resumable SSE."""
    try:
        replay_count = 0
        for seq, raw in event_replay_buffer.snapshot_since(channel_id, floor_seq):
            if seq > baseline_seq:
                continue
            try:
                ev_type = json.loads(raw).get("type", "unknown")
            except Exception:
                ev_type = "unknown"
            yield f"id: {seq}\nevent: {ev_type}\ndata: {raw}\n\n"
            replay_count += 1
        if replay_count:
            logger.info(
                "[SSE] Replayed %d buffered events for %s (floor=%d, baseline=%d)",
                replay_count,
                label,
                floor_seq,
                baseline_seq,
            )
    except Exception:
        logger.exception("[SSE] Replay buffer drain failed for %s", label)


async def _unwrap_broker_message(raw_data: str) -> tuple[str | None, str]:
    """Unwrap broker seq envelope and return (seq, raw_json)."""
    try:
        envelope = json.loads(raw_data)
        if isinstance(envelope, dict) and "_evt_seq" in envelope:
            return str(envelope["_evt_seq"]), envelope["_evt_raw"]
    except Exception:
        pass
    return None, raw_data


async def _workflow_stream_user(
    current_user: User | None, token: str | None
) -> User:
    user = current_user
    if user is None and token:
        member_id = await identity_service.resolve_member_id_from_token(token)
        if member_id:
            user = User(id=member_id, is_active=True)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
        )
    return user


async def _ensure_workflow_access(project_id: int, user: User) -> None:
    if not settings.MULTI_TENANT_MODE:
        return
    async with session_scope() as session:
        result = await session.execute(
            select(Repository.member_id).where(
                Repository.project_id == project_id
            )
        )
        owner_id = result.scalar_one_or_none()
    if owner_id != int(user.id):
        raise HTTPException(status_code=404, detail="workflow not found")


@router.get("/chat/{thread_id}", dependencies=[Depends(verify_guest_access)])
async def stream_chat(thread_id: str, request: Request):
    """
    SSE endpoint to stream chat updates for a thread.
    Uses MessageBroker Pub/Sub for real-time event streaming.

    Event Types:
    - activity: Initial lightweight state snapshot (sent once on connect)
    - artifact: New artifact created/updated (incremental)
    - status: Status change (incremental)
    - token: Token stream for chat
    - message: New message (flat message sync)
    - human_request: HITL request
    - stream: Structured stream events (thinking, errors, etc.)
    """

    async def event_generator():
        pubsub = None

        try:
            # 1. Subscribe to broker channel FIRST to prevent missing events
            broker = get_message_broker()
            # 回放基线：订阅前取当前缓冲 seq——baseline 及之前的事件是
            # 订阅前发布的（实时流必然收不到），只回放这段 → 与实时流
            # 零重叠、无需去重；Last-Event-ID 断点续传也在此区间内裁剪。
            from app.core.engine.message.broker import event_replay_buffer

            baseline_seq = event_replay_buffer.current_seq(thread_id)
            pubsub = broker.pubsub()
            channel = f"chat:{thread_id}:events"
            await pubsub.subscribe(channel)
            logger.info(f"[SSE] Subscribed to Pub/Sub channel via MessageBroker: {channel}")

            # 1.5 回放缓冲（审计修复：新线程竞态/断线重连丢事件）——
            # SSE 原生 Last-Event-ID：EventSource 自动重连时浏览器带
            # Last-Event-ID header（每条事件已带 id: seq）；首次连接无
            # header → 回放整个订阅前窗口。区间 (last_seq, baseline_seq]。
            floor_seq = _parse_last_event_seq(request)
            async for chunk in _replay_buffered(thread_id, floor_seq, baseline_seq, thread_id):
                yield chunk

            # 2. Bootstrap: Send Initial Full State (once)
            try:
                activity = await activity_monitor.get_activity(thread_id)
                logger.debug(f"[SSE] Fetched initial activity for {thread_id}")
            except Exception as e:
                logger.warning(f"[SSE] Initial activity fetch failed for {thread_id} ({type(e).__name__}): {e}. Retrying in 1s...", exc_info=True)
                await asyncio.sleep(1.0)
                activity = await activity_monitor.get_activity(thread_id)

            if activity:
                # activity is an ActivityState Pydantic model.
                # model_dump() ensures nested models are serialized to dicts.
                snapshot = activity.model_dump() if hasattr(activity, "model_dump") else activity
                yield f"event: activity\ndata: {json.dumps(snapshot)}\n\n"
                logger.info(f"[SSE] Sent initial activity snapshot to {thread_id}")

                if snapshot.get("human_request"):
                    yield f"event: human_request\ndata: {json.dumps(snapshot['human_request'])}\n\n"

            # 3. Stream Events (incremental)
            reconnect_attempts = 0
            MAX_RECONNECT_ATTEMPTS = 10
            BASE_BACKOFF = 0.5
            last_heartbeat = asyncio.get_running_loop().time()

            while True:
                try:
                    # Heartbeat to keep connection alive and flush buffers
                    now = asyncio.get_running_loop().time()
                    if now - last_heartbeat > 15.0:
                        yield ": ping\n\n"
                        last_heartbeat = now

                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    # Reset backoff on successful read
                    reconnect_attempts = 0
                except (ConnectionError, asyncio.TimeoutError) as e:
                    # Timeout is normal, loop again for heartbeat
                    if isinstance(e, asyncio.TimeoutError):
                        continue

                    reconnect_attempts += 1
                    if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                        yield f"event: error\ndata: {json.dumps({'error': 'Stream connection lost after maximum retries'})}\n\n"
                        break
                    backoff = min(BASE_BACKOFF * (2 ** (reconnect_attempts - 1)), 30.0)
                    logger.warning(f"[SSE] PubSub read error for {thread_id}: {e}. Re-subscribing in {backoff}s...", exc_info=True)
                    await asyncio.sleep(backoff)
                    await pubsub.subscribe(channel)
                    continue
                except Exception as e:
                    if "Buffer is closed" in str(e):
                        reconnect_attempts += 1
                        if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                            logger.exception(f"[SSE] Cache buffer closed, max retries exceeded for {thread_id}.")
                            yield f"event: error\ndata: {json.dumps({'error': 'Stream connection lost after maximum retries'})}\n\n"
                            break
                        backoff = min(BASE_BACKOFF * (2 ** (reconnect_attempts - 1)), 30.0)
                        logger.exception(f"[SSE] Cache buffer is closed for {thread_id}. Re-initializing in {backoff}s...")
                        await asyncio.sleep(backoff)
                        await pubsub.subscribe(channel)
                        continue
                    raise e

                if message and message["type"] == "message":
                    raw_data = message["data"]
                    if isinstance(raw_data, bytes):
                        raw_data = raw_data.decode("utf-8", errors="replace")

                    # 解包 broker 的 seq 包装（仅 chat channel），实时事件
                    # 标注 id: 使 Last-Event-ID 断点续传完整闭环。
                    evt_seq = None
                    try:
                        maybe = json.loads(raw_data)
                        if isinstance(maybe, dict) and "_evt_seq" in maybe:
                            evt_seq = maybe["_evt_seq"]
                            raw_data = maybe["_evt_raw"]
                    except Exception:
                        pass

                    try:
                        event_data = json.loads(raw_data)
                        event_type = event_data.get("type", "unknown")

                        # 直接透传，WebChannel 保证了输出格式一致性，不进行二次归一化
                        #（回放区间为订阅前窗口，与实时流零重叠，无需去重）
                        seq_line = f"id: {evt_seq}\n" if evt_seq else ""
                        yield f"{seq_line}event: {event_type}\ndata: {raw_data}\n\n"

                    except Exception as e:
                        yield f"event: error\ndata: {json.dumps({'error': 'Failed to process server event', 'details': str(e)})}\n\n"

                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            # 客户端断开连接（SSE 取消）是预期行为，不是错误，无需打印 Traceback。
            logger.info(f"Stream cancelled: {thread_id}")
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if pubsub:
                await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/workflow/{workflow_id}")
async def stream_workflow(
    workflow_id: str,
    request: Request,
    current_user: CurrentUserOptional,
    token: str | None = Query(None),
):
    """
    Stream workflow lifecycle and artifact events.

    Event type: workflow_updated.
    """
    user = await _workflow_stream_user(current_user, token)
    try:
        workflow = await WorkflowService.get_workflow(workflow_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc
    await _ensure_workflow_access(workflow.project_id, user)

    async def event_generator():
        pubsub = None
        try:
            broker = get_message_broker()
            baseline_seq = event_replay_buffer.current_seq(workflow_id)
            pubsub = broker.pubsub()
            channel = f"workflow:{workflow_id}:events"
            await pubsub.subscribe(channel)

            floor_seq = _parse_last_event_seq(request)
            async for chunk in _replay_buffered(workflow_id, floor_seq, baseline_seq, f"workflow:{workflow_id}"):
                yield chunk

            yield (
                "event: workflow_updated\n"
                f'data: {json.dumps({"type": "workflow_updated", "workflow_id": workflow_id, "event": "connected", "status": workflow.status})}\n\n'
            )
            if workflow.status != "running":
                return

            reconnect_attempts = 0
            max_reconnect_attempts = 10
            base_backoff = 0.5
            last_heartbeat = asyncio.get_running_loop().time()

            while True:
                try:
                    now = asyncio.get_running_loop().time()
                    if now - last_heartbeat > 15.0:
                        yield ": ping\n\n"
                        last_heartbeat = now

                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    reconnect_attempts = 0
                except (ConnectionError, asyncio.TimeoutError):
                    continue
                except Exception as exc:
                    if "Buffer is closed" not in str(exc):
                        raise
                    reconnect_attempts += 1
                    if reconnect_attempts > max_reconnect_attempts:
                        yield f"event: error\ndata: {json.dumps({'error': 'Workflow stream connection lost after maximum retries'})}\n\n"
                        break
                    backoff = min(
                        base_backoff * (2 ** (reconnect_attempts - 1)),
                        30.0,
                    )
                    logger.warning(
                        "[SSE] Workflow PubSub read error for %s: %s",
                        workflow_id,
                        exc,
                    )
                    await asyncio.sleep(backoff)
                    await pubsub.subscribe(channel)
                    continue

                if message and message["type"] == "message":
                    raw_data = message["data"]
                    if isinstance(raw_data, bytes):
                        raw_data = raw_data.decode("utf-8", errors="replace")

                    seq_str, raw_data = await _unwrap_broker_message(raw_data)

                    try:
                        event_data = json.loads(raw_data)
                        event_type = event_data.get("type", "unknown")
                        seq_line = f"id: {seq_str}\n" if seq_str else ""
                        yield f"{seq_line}event: {event_type}\ndata: {raw_data}\n\n"
                        terminal_event = (
                            event_data.get("event") == "workflow_status_changed"
                            and event_data.get("status") != "running"
                        )
                    except Exception as exc:
                        yield (
                            "event: error\n"
                            f"data: {json.dumps({'error': 'Failed to process workflow event', 'details': str(exc)})}\n\n"
                        )

                    if terminal_event:
                        break

                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            logger.info("Workflow stream cancelled: %s", workflow_id)
        except Exception as exc:
            logger.exception("Workflow stream error: %s", workflow_id)
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            if pubsub:
                await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tasks")
async def stream_tasks(
    current_user: CurrentUserOptional,
    request: Request,
    token: str | None = Query(None),
    project_id: int | None = Query(None),
):
    """
    Stream task queue lifecycle events.

    Event type: task_queue_updated.
    """
    user = await _workflow_stream_user(current_user, token)
    if project_id is not None and project_id > 0:
        await _ensure_workflow_access(project_id, user)
    elif settings.MULTI_TENANT_MODE:
        # 多租户 fail-closed：无项目归属的全局任务事件流会跨成员泄露
        # （标题/状态/结果摘要），要求显式 project_id（已过 404 校验）
        raise HTTPException(
            status_code=400,
            detail="project_id is required for the task stream in multi-tenant mode",
        )

    channel = (
        f"tasks:{project_id}:events"
        if project_id is not None and project_id > 0
        else "tasks:all:events"
    )
    channel_id = str(project_id) if project_id is not None and project_id > 0 else "all"

    async def event_generator():
        pubsub = None
        try:
            broker = get_message_broker()
            baseline_seq = event_replay_buffer.current_seq(channel_id)
            pubsub = broker.pubsub()
            await pubsub.subscribe(channel)

            floor_seq = _parse_last_event_seq(request)
            async for chunk in _replay_buffered(channel_id, floor_seq, baseline_seq, channel):
                yield chunk

            yield (
                "event: task_queue_updated\n"
                f'data: {json.dumps({"type": "task_queue_updated", "event": "connected", "project_id": project_id})}\n\n'
            )

            reconnect_attempts = 0
            max_reconnect_attempts = 10
            base_backoff = 0.5
            last_heartbeat = asyncio.get_running_loop().time()

            while True:
                try:
                    now = asyncio.get_running_loop().time()
                    if now - last_heartbeat > 15.0:
                        yield ": ping\n\n"
                        last_heartbeat = now

                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    reconnect_attempts = 0
                except (ConnectionError, asyncio.TimeoutError):
                    continue
                except Exception as exc:
                    if "Buffer is closed" not in str(exc):
                        raise
                    reconnect_attempts += 1
                    if reconnect_attempts > max_reconnect_attempts:
                        yield f"event: error\ndata: {json.dumps({'error': 'Task stream connection lost after maximum retries'})}\n\n"
                        break
                    backoff = min(
                        base_backoff * (2 ** (reconnect_attempts - 1)),
                        30.0,
                    )
                    logger.warning(
                        "[SSE] Task PubSub read error for %s: %s",
                        channel,
                        exc,
                    )
                    await asyncio.sleep(backoff)
                    await pubsub.subscribe(channel)
                    continue

                if message and message["type"] == "message":
                    raw_data = message["data"]
                    if isinstance(raw_data, bytes):
                        raw_data = raw_data.decode("utf-8", errors="replace")

                    seq_str, raw_data = await _unwrap_broker_message(raw_data)

                    try:
                        event_data = json.loads(raw_data)
                        event_type = event_data.get("type", "unknown")
                        seq_line = f"id: {seq_str}\n" if seq_str else ""
                        yield f"{seq_line}event: {event_type}\ndata: {raw_data}\n\n"
                    except Exception as exc:
                        yield (
                            "event: error\n"
                            f"data: {json.dumps({'error': 'Failed to process task event', 'details': str(exc)})}\n\n"
                        )

                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            logger.info("Task stream cancelled: %s", channel)
        except Exception as exc:
            logger.exception("Task stream error: %s", channel)
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            if pubsub:
                await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/thread/{thread_id}", dependencies=[Depends(verify_guest_access)])
async def stream_thread(thread_id: str, request: Request):
    """
    SSE endpoint for thread-level realtime updates (duty workbench).

    Event type: thread_updated — published by MessageRepository.persist
    whenever a message lands in this thread (tool outputs, reasoning,
    plan-adjacent steps). Frontend uses it to refresh the execution
    timeline without polling.
    """

    async def event_generator():
        pubsub = None
        try:
            broker = get_message_broker()
            baseline_seq = event_replay_buffer.current_seq(thread_id)
            pubsub = broker.pubsub()
            channel = f"thread:{thread_id}:events"
            await pubsub.subscribe(channel)

            floor_seq = _parse_last_event_seq(request)
            async for chunk in _replay_buffered(thread_id, floor_seq, baseline_seq, f"thread:{thread_id}"):
                yield chunk

            yield (
                "event: thread_updated\n"
                f'data: {json.dumps({"type": "thread_updated", "event": "connected", "thread_id": thread_id})}\n\n'
            )

            last_heartbeat = asyncio.get_running_loop().time()
            while True:
                try:
                    now = asyncio.get_running_loop().time()
                    if now - last_heartbeat > 15.0:
                        yield ": ping\n\n"
                        last_heartbeat = now
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                except (ConnectionError, asyncio.TimeoutError):
                    continue
                except Exception:
                    break
                if message is None:
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", "replace")
                if not data:
                    continue
                seq_str, raw_data = await _unwrap_broker_message(data)
                seq_line = f"id: {seq_str}\n" if seq_str else ""
                yield f"{seq_line}event: thread_updated\ndata: {raw_data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
                except Exception:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/system", dependencies=[Depends(verify_guest_access)])
async def stream_system(request: Request):
    """
    SSE endpoint for system-wide public events.

    Bridges internal events marked with is_public=True and broadcast_channel="system"
    to the frontend. Events are published to the "system:events" pub/sub channel by
    UniversalBridgeSubscriber.

    Event Types (dynamic, matching event.event_type):
    - project.new_detected: New project directory detected
    - indexing.status: Indexing status changed
    - device.connected / device.disconnected: Android mirror device changes
    - synthesis.completed: Smart synthesis finished
    - subscription.changed: Subscription/quota changed
    """

    async def event_generator():
        pubsub = None
        channel = "system:events"
        channel_id = "system"

        try:
            broker = get_message_broker()
            baseline_seq = event_replay_buffer.current_seq(channel_id)
            pubsub = broker.pubsub()
            await pubsub.subscribe(channel)
            logger.info("[SSE] Subscribed to system Pub/Sub channel via MessageBroker: %s", channel)

            floor_seq = _parse_last_event_seq(request)
            async for chunk in _replay_buffered(channel_id, floor_seq, baseline_seq, channel):
                yield chunk

            reconnect_attempts = 0
            MAX_RECONNECT_ATTEMPTS = 10
            BASE_BACKOFF = 0.5
            last_heartbeat = asyncio.get_running_loop().time()

            while True:
                try:
                    now = asyncio.get_running_loop().time()
                    if now - last_heartbeat > 15.0:
                        yield ": ping\n\n"
                        last_heartbeat = now

                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    reconnect_attempts = 0
                except (ConnectionError, asyncio.TimeoutError) as e:
                    if isinstance(e, asyncio.TimeoutError):
                        continue

                    reconnect_attempts += 1
                    if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                        yield f"event: error\ndata: {json.dumps({'error': 'System stream connection lost after maximum retries'})}\n\n"
                        break
                    backoff = min(BASE_BACKOFF * (2 ** (reconnect_attempts - 1)), 30.0)
                    logger.warning("[SSE] PubSub read error for system stream: %s. Re-subscribing in %ss...", e, backoff, exc_info=True)
                    await asyncio.sleep(backoff)
                    await pubsub.subscribe(channel)
                    continue
                except Exception as e:
                    if "Buffer is closed" in str(e):
                        reconnect_attempts += 1
                        if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                            logger.error("[SSE] System stream cache buffer closed, max retries exceeded.")
                            yield f"event: error\ndata: {json.dumps({'error': 'System stream connection lost after maximum retries'})}\n\n"
                            break
                        backoff = min(BASE_BACKOFF * (2 ** (reconnect_attempts - 1)), 30.0)
                        logger.exception("[SSE] System stream cache buffer is closed. Re-initializing in %ss...", backoff)
                        await asyncio.sleep(backoff)
                        await pubsub.subscribe(channel)
                        continue
                    raise e

                if message and message["type"] == "message":
                    raw_data = message["data"]
                    if isinstance(raw_data, bytes):
                        raw_data = raw_data.decode("utf-8", errors="replace")

                    seq_str, raw_data = await _unwrap_broker_message(raw_data)
                    try:
                        event_data = json.loads(raw_data)
                        event_type = event_data.get("type", "unknown")
                        seq_line = f"id: {seq_str}\n" if seq_str else ""
                        yield f"{seq_line}event: {event_type}\ndata: {raw_data}\n\n"
                    except Exception as e:
                        yield f"event: error\ndata: {json.dumps({'error': 'Failed to process system event', 'details': str(e)})}\n\n"

                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            logger.info("System stream cancelled")
        except Exception as e:
            logger.error("System stream error: %s", e, exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if pubsub:
                await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
