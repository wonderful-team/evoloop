"""
SSE (Server-Sent Events) streaming endpoint for real-time chat updates.
Streams tokens and activity updates as they happen.
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.core.monitoring.activity import activity_monitor
from app.api.deps import verify_guest_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])


@router.get("/chat/{thread_id}", dependencies=[Depends(verify_guest_access)])
async def stream_chat(thread_id: str):
    """
    SSE endpoint to stream chat updates for a thread.
    
    Emits events:
    - token: New LLM token
    - task: Task update (start/done/failed)
    - status: Overall status change
    - done: Stream complete
    """
    
    async def event_generator():
        """Generate SSE events from activity monitor."""
        last_content_length = 0
        check_count = 0
        max_checks = 600  # 5 minutes at 500ms intervals
        
        while check_count < max_checks:
            try:
                activity = await activity_monitor.get_activity(thread_id)
                
                if not activity:
                    # Thread not found or not started yet
                    yield f"event: waiting\ndata: {json.dumps({'status': 'waiting'})}\n\n"
                    await asyncio.sleep(0.5)
                    check_count += 1
                    continue
                
                status = activity.get("status", "unknown")
                tasks = activity.get("tasks", [])
                
                # Find AI streaming task
                ai_task = None
                for task in tasks:
                    if task.get("type") == "ai" and task.get("status") == "running":
                        ai_task = task
                        break
                
                # Emit new tokens
                if ai_task and ai_task.get("details"):
                    details = ai_task["details"]
                    if len(details) > last_content_length:
                        new_tokens = details[last_content_length:]
                        last_content_length = len(details)
                        yield f"event: token\ndata: {json.dumps({'content': new_tokens})}\n\n"
                
                # Emit Human Request (Separate Event)
                human_req = activity.get("human_request")
                # Initialize tracker if not exists
                if 'last_req_id' not in locals():
                    last_req_id = None
                    
                if human_req:
                    req_id = human_req.get("id")
                    if last_req_id != req_id:
                        yield f"event: human_request\ndata: {json.dumps(human_req)}\n\n"
                        last_req_id = req_id
                
                # Emit Activity Update (if changed)
                # We construct a snapshot of what frontend needs
                current_activity_snapshot = {
                    "tasks": tasks,
                    "artifacts": activity.get("artifacts", []),
                    "agent_state": activity.get("agent_state", {}),
                    "verification": activity.get("verification", {}),
                    "status": status
                }
                
                # Simple serialization to check changes (could be optimized)
                # We need to track last_activity_str outside loop
                current_activity_str = json.dumps(current_activity_snapshot, sort_keys=True)
                
                # We need to initialize last_activity_str before loop
                if 'last_activity_str' not in locals():
                     last_activity_str = ""

                if current_activity_str != last_activity_str:
                     yield f"event: activity\ndata: {current_activity_str}\n\n"
                     yield f"event: status\ndata: {json.dumps({'status': status})}\n\n"
                     last_activity_str = current_activity_str

                # Check if done - CHANGED for Arch 2.0: Do not disconnect.
                # Just emit the status update (handled above)
                # if status not in ["running", "SUMMARIZING", "INDEXING"]:
                #     yield f"event: done\ndata: {json.dumps({'status': status})}\n\n"
                #     break

                    
                await asyncio.sleep(0.3)  # 300ms polling
                check_count += 1
                
            except asyncio.CancelledError:
                logger.info(f"SSE stream cancelled for {thread_id}")
                break
            except Exception as e:
                logger.error(f"SSE error for {thread_id}: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(1)
                check_count += 1
        
        yield f"event: done\ndata: {json.dumps({'reason': 'timeout'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
