"""
SSE (Server-Sent Events) streaming endpoint for real-time chat updates.
Streams tokens and activity updates as they happen.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import verify_guest_access
from app.core.monitoring.activity import activity_monitor
from app.core.engine.message.broker import get_message_broker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])


@router.get("/chat/{thread_id}", dependencies=[Depends(verify_guest_access)])
async def stream_chat(thread_id: str):
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
            pubsub = broker.pubsub()
            channel = f"chat:{thread_id}:events"
            await pubsub.subscribe(channel)
            logger.info(f"[SSE] Subscribed to Pub/Sub channel via MessageBroker: {channel}")

            # 2. Bootstrap: Send Initial Full State (once)
            try:
                activity = await activity_monitor.get_activity(thread_id)
                logger.debug(f"[SSE] Fetched initial activity for {thread_id}")
            except Exception as e:
                logger.warning(f"[SSE] Initial activity fetch failed for {thread_id} ({type(e).__name__}): {e}. Retrying in 1s...")
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
                    logger.warning(f"[SSE] PubSub read error for {thread_id}: {e}. Re-subscribing in {backoff}s...")
                    await asyncio.sleep(backoff)
                    await pubsub.subscribe(channel)
                    continue
                except Exception as e:
                    if "Buffer is closed" in str(e):
                        reconnect_attempts += 1
                        if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                            logger.error(f"[SSE] Cache buffer closed, max retries exceeded for {thread_id}.")
                            yield f"event: error\ndata: {json.dumps({'error': 'Stream connection lost after maximum retries'})}\n\n"
                            break
                        backoff = min(BASE_BACKOFF * (2 ** (reconnect_attempts - 1)), 30.0)
                        logger.error(f"[SSE] Cache buffer is closed for {thread_id}. Re-initializing in {backoff}s...")
                        await asyncio.sleep(backoff)
                        await pubsub.subscribe(channel)
                        continue
                    raise e

                if message and message["type"] == "message":
                    raw_data = message["data"]

                    try:
                        event_data = json.loads(raw_data)
                        event_type = event_data.get("type", "unknown")

                        # 直接透传，WebChannel 保证了输出格式一致性，不进行二次归一化
                        yield f"event: {event_type}\ndata: {raw_data}\n\n"

                    except Exception as e:
                        yield f"event: error\ndata: {json.dumps({'error': 'Failed to process server event', 'details': str(e)})}\n\n"

                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
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
    - todo.updated: Todo list changed
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
                    logger.warning(f"[SSE] PubSub read error for system stream: {e}. Re-subscribing in {backoff}s...")
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
                        logger.error(f"[SSE] System stream cache buffer is closed. Re-initializing in {backoff}s...")
                        await asyncio.sleep(backoff)
                        await pubsub.subscribe(channel)
                        continue
                    raise e

                if message and message["type"] == "message":
                    raw_data = message["data"]

                    try:
                        event_data = json.loads(raw_data)
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
