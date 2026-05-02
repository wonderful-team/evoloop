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
from app.core.engine.message.folder import MessageNormalizer
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.cache import cache
from app.models.schemas.events import StreamEventType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])

# Pre-compute set of all stream event type values for fast membership testing
_STREAM_EVENT_TYPE_VALUES = {e.value for e in StreamEventType}


@router.get("/chat/{thread_id}", dependencies=[Depends(verify_guest_access)])
async def stream_chat(thread_id: str):
    """
    SSE endpoint to stream chat updates for a thread.
    Uses cache Pub/Sub for real-time event streaming.
    
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
        logger.info(f"[SSE] New connection request for thread: {thread_id}")
        
        try:
            # 1. Bootstrap: Send Initial Full State (once)
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

            # 2. Subscribe to cache channel
            pubsub = cache.pubsub()
            channel = f"chat:{thread_id}:events"
            await pubsub.subscribe(channel)
            logger.info(f"[SSE] Subscribed to Pub/Sub channel: {channel}")

            # 3. Stream Events (incremental)
            reconnect_attempts = 0
            MAX_RECONNECT_ATTEMPTS = 10
            BASE_BACKOFF = 0.5
            last_heartbeat = asyncio.get_event_loop().time()

            while True:
                try:
                    # Heartbeat to keep connection alive and flush buffers
                    now = asyncio.get_event_loop().time()
                    if now - last_heartbeat > 15.0:
                        yield ": ping\n\n"
                        last_heartbeat = now
                        logger.debug(f"[SSE] Sent keep-alive ping for {thread_id}")

                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    # Reset backoff on successful read
                    reconnect_attempts = 0
                except (ConnectionError, asyncio.TimeoutError) as e:
                    # Timeout is normal, loop again for heartbeat
                    if isinstance(e, asyncio.TimeoutError):
                        continue
                        
                    reconnect_attempts += 1
                    if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                        logger.error(f"[SSE] PubSub max reconnect attempts ({MAX_RECONNECT_ATTEMPTS}) exceeded for {thread_id}. Aborting.")
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
                    logger.info(f"[SSE] Raw Pub/Sub message received for {thread_id}: len={len(raw_data)}, preview={raw_data[:150]}...")

                    try:
                        event_data = json.loads(raw_data)
                        event_type = event_data.get("type", "unknown")
                        logger.info(f"[SSE] Parsed event_type={event_type}, keys={list(event_data.keys())}")

                        # Incremental updates: forward events directly without re-fetching
                        if event_type == "artifact":
                            yield f"event: artifact\ndata: {json.dumps(event_data)}\n\n"
                        
                        elif event_type == "status":
                            yield f"event: status\ndata: {json.dumps(event_data)}\n\n"
                        
                        elif event_type == "token":
                            content = event_data.get("content")
                            if content:
                                yield f"event: token\ndata: {json.dumps({'content': content})}\n\n"
                        
                        elif event_type == "message":
                            msg_data = event_data.get('data', {})
                            msg_role = msg_data.get('role', '')
                            logger.info(f"[SSE] YIELDING message event: role={msg_role}, content_len={len(msg_data.get('content',''))}")
                            msg_data = MessageNormalizer.normalize_dict(msg_data)

                            yield f"event: message\ndata: {json.dumps(msg_data)}\n\n"
                        
                        elif event_type == "human_request":
                            yield f"event: human_request\ndata: {json.dumps(event_data.get('data'))}\n\n"

                        elif event_type in _STREAM_EVENT_TYPE_VALUES:
                            yield f"event: stream\ndata: {json.dumps(event_data)}\n\n"

                    except Exception as e:
                        logger.error(f"[SSE] Error processing pubsub message for {thread_id}: {e}")
                        # Notify client that an event was lost
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
