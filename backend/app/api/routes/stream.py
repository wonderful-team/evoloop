"""
SSE (Server-Sent Events) streaming endpoint for real-time chat updates.
Streams tokens and activity updates as they happen.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import verify_guest_access
from app.core.engine.message.broker import get_message_broker
from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])


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
            try:
                last_event_id = request.headers.get("last-event-id")
                floor_seq = (
                    int(last_event_id)
                    if last_event_id and last_event_id.isdigit()
                    else 0
                )
                replay_count = 0
                for seq, raw in event_replay_buffer.snapshot_since(thread_id, floor_seq):
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
                        f"[SSE] Replayed {replay_count} buffered events for {thread_id} (floor={floor_seq}, baseline={baseline_seq})"
                    )
            except Exception:
                logger.exception(f"[SSE] Replay buffer drain failed for {thread_id}")

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


@router.get("/system", dependencies=[Depends(verify_guest_access)])
async def stream_system():
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

        try:
            broker = get_message_broker()
            pubsub = broker.pubsub()
            channel = "system:events"
            await pubsub.subscribe(channel)
            logger.info(f"[SSE] Subscribed to system Pub/Sub channel via MessageBroker: {channel}")

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
                    logger.warning(f"[SSE] PubSub read error for system stream: {e}. Re-subscribing in {backoff}s...", exc_info=True)
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
                        logger.exception(f"[SSE] System stream cache buffer is closed. Re-initializing in {backoff}s...")
                        await asyncio.sleep(backoff)
                        await pubsub.subscribe(channel)
                        continue
                    raise e

                if message and message["type"] == "message":
                    raw_data = message["data"]

                    try:
                        json.loads(raw_data)
                        yield f"data: {raw_data}\n\n"
                    except Exception as e:
                        yield f"event: error\ndata: {json.dumps({'error': 'Failed to process system event', 'details': str(e)})}\n\n"

                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            logger.info("System stream cancelled")
        except Exception as e:
            logger.error(f"System stream error: {e}", exc_info=True)
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
