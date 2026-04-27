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
from app.core.engine.message.folder import MessageFolder
from app.core.engine.state.history import ToolStep
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
    - activity: Initial full state snapshot (sent once on connect)
    - step: New step created/updated (incremental)
    - artifact: New artifact created/updated (incremental)
    - status: Status change (incremental)
    - token: Token stream for chat
    - message: New message (with tool folding)
    - human_request: HITL request
    - stream: Structured stream events (thinking, tool_progress, etc.)
    """

    async def event_generator():
        pubsub = None
        # Track last AI message for server-side tool folding
        last_ai_message = None
        
        try:
            # 1. Bootstrap: Send Initial Full State (once)
            try:
                activity = await activity_monitor.get_activity(thread_id)
            except Exception as e:
                logger.warning(f"Initial activity fetch failed ({type(e).__name__}): {e}. Retrying in 1s...")
                await asyncio.sleep(1.0)
                activity = await activity_monitor.get_activity(thread_id)

            if activity:
                # activity is an ActivityState Pydantic model. 
                # model_dump() ensures nested ActivityStep/ActivityArtifact models are serialized to dicts.
                snapshot = activity.model_dump() if hasattr(activity, "model_dump") else activity
                yield f"event: activity\ndata: {json.dumps(snapshot)}\n\n"

                if snapshot.get("human_request"):
                    yield f"event: human_request\ndata: {json.dumps(snapshot['human_request'])}\n\n"

            # 2. Subscribe to cache channel
            pubsub = cache.pubsub()
            await pubsub.subscribe(f"chat:{thread_id}:events")

            # 3. Stream Events (incremental)
            reconnect_attempts = 0
            MAX_RECONNECT_ATTEMPTS = 10
            BASE_BACKOFF = 0.5

            while True:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    # Reset backoff on successful read
                    reconnect_attempts = 0
                except (ConnectionError, asyncio.TimeoutError) as e:
                    reconnect_attempts += 1
                    if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                        logger.error(f"PubSub max reconnect attempts ({MAX_RECONNECT_ATTEMPTS}) exceeded. Aborting stream.")
                        yield f"event: error\ndata: {json.dumps({'error': 'Stream connection lost after maximum retries'})}\n\n"
                        break
                    backoff = min(BASE_BACKOFF * (2 ** (reconnect_attempts - 1)), 30.0)
                    logger.warning(f"PubSub read error: {e}. Re-subscribing in {backoff}s (attempt {reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS})...")
                    await asyncio.sleep(backoff)
                    await pubsub.subscribe(f"chat:{thread_id}:events")
                    continue
                except Exception as e:
                    if "Buffer is closed" in str(e):
                        reconnect_attempts += 1
                        if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                            logger.error(f"PubSub max reconnect attempts ({MAX_RECONNECT_ATTEMPTS}) exceeded. Aborting stream.")
                            yield f"event: error\ndata: {json.dumps({'error': 'Stream connection lost after maximum retries'})}\n\n"
                            break
                        backoff = min(BASE_BACKOFF * (2 ** (reconnect_attempts - 1)), 30.0)
                        logger.error(f"Cache buffer is closed. Re-initializing connection in {backoff}s (attempt {reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS})...")
                        await asyncio.sleep(backoff)
                        await pubsub.subscribe(f"chat:{thread_id}:events")
                        continue
                    raise e

                if message and message["type"] == "message":
                    raw_data = message["data"]

                    try:
                        event_data = json.loads(raw_data)
                        event_type = event_data.get("type", "unknown")

                        # Incremental updates: forward events directly without re-fetching
                        if event_type == "step":
                            yield f"event: step\ndata: {json.dumps(event_data)}\n\n"
                        
                        elif event_type == "artifact":
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
                            msg_type = msg_data.get('type', '')
                            
                            # Server-side Tool Message Folding
                            if msg_role == 'tool' or msg_type == 'tool':
                                if last_ai_message:
                                    # Deep-copy to avoid mutating the shared reference
                                    folded = dict(last_ai_message)
                                    MessageFolder.append_tool_event_to_ai_message(folded, msg_data)
                                    yield f"event: message\ndata: {json.dumps(folded)}\n\n"
                                else:
                                    # Orphan tool message — forward as-is so frontend can display it
                                    yield f"event: message\ndata: {json.dumps(msg_data)}\n\n"
                            else:
                                if msg_role == 'ai':
                                    # Ensure steps is a list without clobbering non-list data
                                    if not msg_data.get('steps'):
                                        msg_data['steps'] = []
                                    last_ai_message = msg_data
                                yield f"event: message\ndata: {json.dumps(msg_data)}\n\n"
                        
                        elif event_type == "human_request":
                            yield f"event: human_request\ndata: {json.dumps(event_data.get('data'))}\n\n"
                        
                        # Enhanced Stream Events (thinking, tool progress, errors, etc.)
                        # Also includes error events that need user notification
                        elif event_type in _STREAM_EVENT_TYPE_VALUES:
                            yield f"event: stream\ndata: {json.dumps(event_data)}\n\n"

                    except Exception as e:
                        logger.error(f"Error processing pubsub message: {e}")
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
