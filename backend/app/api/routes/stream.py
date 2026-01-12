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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])


@router.get("/chat/{thread_id}", dependencies=[Depends(verify_guest_access)])
async def stream_chat(thread_id: str):
    """
    SSE endpoint to stream chat updates for a thread.
    Uses Redis Pub/Sub for real-time event streaming.
    """

    async def event_generator():
        client = None
        pubsub = None
        try:
            # 1. Bootstrap: Send Initial Full State
            # This ensures frontend is up-to-date even if it missed events
            activity = await activity_monitor.get_activity(thread_id)
            if activity:
                # Construct snapshot using the same structure as before (for compatibility or manual merge)
                snapshot = {
                    "tasks": activity.get("tasks", []),
                    "artifacts": activity.get("artifacts", []),
                    "agent_state": activity.get("agent_state", {}),
                    "active_memories": activity.get("active_memories", []),
                    "verification": activity.get("verification", {}),
                    "status": activity.get("status", "unknown"),
                    "human_request": activity.get("human_request") # Include here
                }
                yield f"event: activity\ndata: {json.dumps(snapshot)}\n\n"

                # Check Human Request immediately
                if activity.get("human_request"):
                     yield f"event: human_request\ndata: {json.dumps(activity['human_request'])}\n\n"

            # 2. Subscribe to Redis Channel
            client = await activity_monitor.get_client()
            pubsub = client.pubsub()
            await pubsub.subscribe(f"chat:{thread_id}:events")

            # 3. Stream Events
            # We use a loop with a small timeout on get_message to allow checking for cancellation
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                if message and message["type"] == "message":
                    # Raw event JSON from backend
                    raw_data = message["data"] # This is a string (JSON)

                    try:
                        # We parse it just to route it correctly if needed, or forward directly
                        # The backend now sends Pydantic .json() strings.
                        # { "type": "task", "action": "create", "id": 1, ... }
                        event_data = json.loads(raw_data)
                        event_type = event_data.get("type", "unknown")

                        # In Phase 3, we simply forward these as specific SSE events
                        # Frontend currently listens to: token, activity, human_request, status, done, error
                        # WE NEED COMPATIBILITY ADAPTER HERE unless we upgrade frontend immediately.

                        # Compatibility Strategy:
                        # For "token" -> emit 'event: token'
                        # For others -> We should ideally trigger a re-fetch or construct a patch.
                        # BUT, for this refactor to work with EXISTING frontend, we have a problem:
                        # The existing frontend expects "event: activity" with FULL SNAPSHOT.
                        # If we only send deltas, the frontend won't update the lists.

                        # Temporary Hybrid Mode:
                        # If we receive a Task/Artifact/State event, we FETCH the full state again and send it.
                        # This turns "Polling" into "Push-Triggered Polling".
                        # It is still 100x better than blind polling.
                        # Once Frontend is updated (Phase 4), we will send the raw delta.

                        # Let's verify if Token is handled
                        if event_type == "token":
                             # Token events in ActivityMonitor are not actually published separately yet?
                             # Wait, look at TransparentCallbackHandler.
                             # It calls monitor.update_task... which publishes 'task' update.
                             # It does NOT publish 'token' event specifically.
                             # Ah, `monitor.update_task` sends `TaskEvent(action="update")`.
                             # The `details` field contains the text? No, `details` is full text.
                             pass

                        # -- HYBRID ADAPTER --
                        # Trigger full Snapshot emit on structural change
                        state_changing_events = ["task", "artifact", "state", "status"]
                        if event_type in state_changing_events:
                             # Re-fetch full activity (Fast, local redis)
                             # This implementation is "Push-Triggered Broadcast"
                             current = await activity_monitor.get_activity(thread_id)
                             snapshot = {
                                "tasks": current.get("tasks", []),
                                "artifacts": current.get("artifacts", []),
                                "agent_state": current.get("agent_state", {}),
                                "active_memories": current.get("active_memories", []),
                                "verification": current.get("verification", {}),
                                "status": current.get("status", "unknown")
                             }
                             yield f"event: activity\ndata: {json.dumps(snapshot)}\n\n"

                             if event_type == "status":
                                 yield f"event: status\ndata: {json.dumps({'status': current['status']})}\n\n"

                        # Forward Token Logic Direct from Event
                        if event_type == "token":
                             content = event_data.get("content")
                             if content:
                                 yield f"event: token\ndata: {json.dumps({'content': content})}\n\n"

                    except Exception as e:
                        logger.error(f"Error processing pubsub message: {e}")

                # Maintain the "Token Polling" for now?
                # Mixing PubSub blocking with Polling is hard unless we use `asyncio.wait_for`.
                # Let's add a specialized Token Handling.

                # Check tokens "frequently"?
                # Better: Modify ActivityMonitor to publish TokenEvents.
                # See next step. For now, let's implement the skeleton.

                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled: {thread_id}")
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if pubsub:
                await pubsub.close()
            if client:
                await client.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
