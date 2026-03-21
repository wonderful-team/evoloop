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
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])


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
                snapshot = {
                    "steps": activity.get("steps", []),
                    "artifacts": activity.get("artifacts", []),
                    "agent_state": activity.get("agent_state", {}),
                    "active_memories": activity.get("active_memories", []),
                    "verification": activity.get("verification", {}),
                    "status": activity.get("status", "unknown"),
                    "human_request": activity.get("human_request"),
                    "final_outcome": activity.get("final_outcome", ""),
                }
                yield f"event: activity\ndata: {json.dumps(snapshot)}\n\n"

                if activity.get("human_request"):
                    yield f"event: human_request\ndata: {json.dumps(activity['human_request'])}\n\n"

            # 2. Subscribe to cache channel
            pubsub = cache.pubsub()
            await pubsub.subscribe(f"chat:{thread_id}:events")

            # 3. Stream Events (incremental)
            while True:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                except (ConnectionError, asyncio.TimeoutError) as e:
                    logger.warning(f"PubSub read error: {e}. Attempting to re-subscribe...")
                    await asyncio.sleep(0.5)
                    await pubsub.subscribe(f"chat:{thread_id}:events")
                    continue
                except Exception as e:
                    if "Buffer is closed" in str(e):
                        logger.error("Cache buffer is closed. Re-initializing connection...")
                        await asyncio.sleep(1.0)
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
                                    existing_steps = last_ai_message.get('steps', [])
                                    step_index = len(existing_steps)
                                    tool_calls = last_ai_message.get('tool_calls', [])
                                    
                                    tool_name = 'Unknown Tool'
                                    tool_input = {}
                                    if tool_calls and step_index < len(tool_calls):
                                        call = tool_calls[step_index]
                                        tool_name = call.get('name', 'Tool')
                                        tool_input = call.get('args', {})
                                    
                                    step = {
                                        'id': msg_data.get('id') or f'step-{asyncio.get_event_loop().time()}',
                                        'tool': tool_name,
                                        'input': tool_input,
                                        'output': msg_data.get('content', ''),
                                        'status': 'success',
                                        'duration': 0,
                                    }
                                    
                                    if 'steps' not in last_ai_message:
                                        last_ai_message['steps'] = []
                                    last_ai_message['steps'].append(step)
                                    
                                    yield f"event: message\ndata: {json.dumps(last_ai_message)}\n\n"
                                else:
                                    logger.warning(f"[Stream] Orphan tool message received: {msg_data.get('id')}")
                            else:
                                if msg_role == 'ai':
                                    msg_data['steps'] = msg_data.get('steps', [])
                                    last_ai_message = msg_data
                                yield f"event: message\ndata: {json.dumps(msg_data)}\n\n"
                        
                        elif event_type == "human_request":
                            yield f"event: human_request\ndata: {json.dumps(event_data.get('data'))}\n\n"
                        
                        elif event_type in ["thinking", "tool_start", "tool_progress", "tool_complete", "tool_error", "checkpoint", "progress", "complete"]:
                            yield f"event: stream\ndata: {json.dumps(event_data)}\n\n"

                    except Exception as e:
                        logger.error(f"Error processing pubsub message: {e}")

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
