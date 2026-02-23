import json
import logging
import time
from typing import Any

from app.infrastructure.database.redis import redis_client
from app.models.schemas.events import (
    AgentStateEvent,
    ArtifactEvent,
    HumanRequestEvent,
    StatusEvent,
    StepEvent,
)

logger = logging.getLogger(__name__)


class ActivityMonitor:
    _instance = None

    def __init__(self):
        pass

    @property
    def client(self):
        """Legacy compatibility for redis_client access."""
        return redis_client

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start_run(self, thread_id: str, main_goal: str = "处理用户请求"):
        key = f"activity:{thread_id}"
        now = time.time()
        data = {
            "status": "running",
            "main_goal": main_goal,
            "agent_state": json.dumps({}),
            "verification": json.dumps({}),
            "steps": json.dumps([]),
            "artifacts": json.dumps([]),
            "active_memories": json.dumps([]),  # Phase 7: Track active memory references
            "updated_at": now,
        }
        # Use HSET
        await redis_client.hset(key, mapping=data)
        # Expiry 24h
        await redis_client.expire(key, 86400)

    async def end_run(self, thread_id: str, status="done"):
        key = f"activity:{thread_id}"
        # Check current status first to handle stopping->cancelled
        current_status = await redis_client.hget(key, "status")

        final_status = status
        if current_status == "stopping":
            final_status = "cancelled"

        await redis_client.hset(
            key, mapping={"status": final_status, "updated_at": time.time()}
        )

        # Mark running steps as done/cancelled
        steps_json = await redis_client.hget(key, "steps")
        if steps_json:
            steps = json.loads(steps_json)
            modified = False
            for t in steps:
                if t["status"] == "running":
                    t["status"] = "cancelled" if final_status == "cancelled" else "done"
                    modified = True
            if modified:
                await redis_client.hset(key, "steps", json.dumps(steps))

                # Publish update events for modified steps
                # Simplification: Just publish the end-run status for now or iterate
                # Iterate to be precise
                for t in steps:
                    if t["status"] in ["done", "cancelled"] and t.get(
                        "start_time"
                    ):  # It was running
                        await redis_client.publish(
                            f"chat:{thread_id}:events",
                            StepEvent(
                                action="update",
                                id=t["id"],
                                data={"status": t["status"]},
                            ).json(),
                        )

        # Publish Status Change
        await redis_client.publish(
            f"chat:{thread_id}:events", StatusEvent(status=final_status).json()
        )

    async def stop_run(self, thread_id: str):
        """Signal a run to stop."""
        key = f"activity:{thread_id}"
        if await redis_client.exists(key):
            await redis_client.hset(
                key, mapping={"status": "stopping", "updated_at": time.time()}
            )

    async def check_cancellation(self, thread_id: str):
        """Check if run is marked for stopping and raise exception if so."""
        from app.core.exceptions import AgentCancelledException

        key = f"activity:{thread_id}"
        status = await redis_client.hget(key, "status")
        if status == "stopping":
            raise AgentCancelledException(f"Run {thread_id} cancelled by user")

    async def set_interrupted(
        self, thread_id: str, reason: str = "awaiting_human_input"
    ):
        """Mark a run as interrupted (paused for human input)."""
        key = f"activity:{thread_id}"
        if await redis_client.exists(key):
            await redis_client.hset(
                key,
                mapping={
                    "status": "interrupted",
                    "interrupt_reason": reason,
                    "updated_at": time.time(),
                },
            )

    async def set_human_request(self, thread_id: str, request_data: dict[str, Any]):
        """
        Store a structured Human Request (HITL).
        Replaces simple 'set_interrupted' for rich interactions.
        """
        key = f"activity:{thread_id}"
        if await redis_client.exists(key):
            await redis_client.hset(
                key,
                mapping={
                    "status": "interrupted",
                    "human_request": json.dumps(request_data),
                    "interrupt_reason": request_data.get(
                        "prompt", "Human Input Required"
                    ),
                    "updated_at": time.time(),
                },
            )

            # Publish Event
            await redis_client.publish(
                f"chat:{thread_id}:events",
                HumanRequestEvent(action="create", data=request_data).json(),
            )

    async def clear_human_request(self, thread_id: str):
        """Clear human request upon resumption."""
        key = f"activity:{thread_id}"
        if await redis_client.exists(key):
            # We don't delete the key, just clear the field and set status to running
            await redis_client.hset(
                key,
                mapping={
                    "status": "running",
                    "human_request": "",  # Clear it
                    "interrupt_reason": "",
                    "updated_at": time.time(),
                },
            )

            # Publish Event
            await redis_client.publish(
                f"chat:{thread_id}:events",
                HumanRequestEvent(action="clear", data={}).json(),
            )

    async def set_active_memory(self, thread_id: str, memory_id: str, memory_name: str):
        """Phase 7: Track which memory is currently being accessed by the Agent."""
        key = f"activity:{thread_id}"
        if not await redis_client.exists(key):
            return

        memories_json = await redis_client.hget(key, "active_memories")
        memories = json.loads(memories_json) if memories_json else []

        # Add if not already in list
        if not any(m.get("id") == memory_id for m in memories):
            memories.append({"id": memory_id, "name": memory_name})
            await redis_client.hset(
                key,
                mapping={
                    "active_memories": json.dumps(memories),
                    "updated_at": time.time(),
                },
            )

    async def clear_active_memories(self, thread_id: str):
        """Clear active memory highlights at end of run."""
        key = f"activity:{thread_id}"
        if await redis_client.exists(key):
            await redis_client.hset(key, "active_memories", json.dumps([]))

    async def add_step(
        self, thread_id: str, name: str, step_type="node", parent_id: int = None
    ):
        key = f"activity:{thread_id}"

        # Use a lock to prevent Race Conditions on the JSON list
        lock_key = f"lock:{key}"
        # We need a dedicated client for locking usually, or just use the same one.
        # redis-py lock is robust.

        try:
            async with redis_client.lock(lock_key, timeout=2.0, blocking_timeout=1.0):
                if not await redis_client.exists(key):
                    return None

                steps_json = await redis_client.hget(key, "steps")
                steps = json.loads(steps_json) if steps_json else []

                if not name:
                    return None

                step_id = len(steps) + 1
                new_step = {
                    "id": step_id,
                    "name": name,
                    "status": "running",
                    "type": step_type,
                    "parent_id": parent_id,
                    "start_time": time.time(),
                    "time": "0s",
                }
                steps.append(new_step)

                await redis_client.hset(
                    key, mapping={"steps": json.dumps(steps), "updated_at": time.time()}
                )

                # Publish Event
                await redis_client.publish(
                    f"chat:{thread_id}:events",
                    StepEvent(action="create", id=step_id, data=new_step).json(),
                )

                return step_id
        except Exception:
            # logger.error(f"Failed to add task: {e}")
            return None

    async def update_step(
        self, thread_id: str, step_id: int, status: str, details: str = None
    ):
        key = f"activity:{thread_id}"
        lock_key = f"lock:{key}"

        try:
            async with redis_client.lock(lock_key, timeout=2.0, blocking_timeout=1.0):
                # We need to fetch, modify, save.
                steps_json = await redis_client.hget(key, "steps")
                if not steps_json:
                    return

                steps = json.loads(steps_json)
                modified = False

                for step in steps:
                    if step["id"] == step_id:
                        step["status"] = status
                        if details:
                            step["details"] = details
                        if status in ["done", "failed"]:
                            duration = time.time() - step["start_time"]
                            step["time"] = f"{duration:.2f}s"
                        modified = True
                        break

                if modified:
                    await redis_client.hset(
                        key,
                        mapping={"steps": json.dumps(steps), "updated_at": time.time()},
                    )

                    # Publish Event
                    # We accept 'details' might mean partial update, but our schema is flexible
                    update_data = {"status": status}
                    if details:
                        update_data["details"] = details
                    await redis_client.publish(
                        f"chat:{thread_id}:events",
                        StepEvent(action="update", id=step_id, data=update_data).json(),
                    )
        except Exception:
            pass

    async def update_agent_state(
        self, thread_id: str, mode: str, task_name: str, task_status: str, details: dict[str, Any] = None
    ):
        # New method to sync Agent State (Sidebar info)
        key = f"activity:{thread_id}"
        state = {
            "mode": mode,
            "task_name": task_name,
            "task_status": task_status,
        }
        if details:
            state["details"] = details

        await redis_client.hset(key, "agent_state", json.dumps(state))

        # Publish Event
        await redis_client.publish(
            f"chat:{thread_id}:events", AgentStateEvent(data=state).json()
        )

    async def log_event(self, event_type: str, data: dict[str, Any], thread_id: str = "system"):
        """Generic event logger for system and session events."""
        key = f"events:{thread_id}:{event_type}"
        timestamp = time.time()
        payload = {
            "type": event_type,
            "data": data,
            "timestamp": timestamp
        }
        
        # Log to a system list in Redis for persistence
        await redis_client.lpush(f"system:logs:{event_type}", json.dumps(payload))
        await redis_client.ltrim(f"system:logs:{event_type}", 0, 99) # Keep last 100
        
        # Publish to the chat stream if it's a session event
        if thread_id != "system":
            await redis_client.publish(
                f"chat:{thread_id}:events", 
                json.dumps({"event": "system_log", "data": payload})
            )
        
        logger.info(f"[ActivityMonitor] Event logged: {event_type}")

    async def add_artifact(
        self,
        thread_id: str,
        name: str,
        artifact_type: str,
        status="created",
        path: str = None,
    ):
        key = f"activity:{thread_id}"
        arts_json = await redis_client.hget(key, "artifacts")
        artifacts = json.loads(arts_json) if arts_json else []

        # Check uniqueness
        for art in artifacts:
            if art["name"] == name:
                art["status"] = "modified"
                await redis_client.hset(key, "artifacts", json.dumps(artifacts))
                # Publish Event for modification
                await redis_client.publish(
                    f"chat:{thread_id}:events",
                    ArtifactEvent(action="update", name=name, data=art).json(),
                )
                return

        artifacts.append(
            {
                "id": len(artifacts) + 1,
                "name": name,
                "type": artifact_type,
                "status": status,
                "path": path,
                "icon": "FileCode",
            }
        )

        await redis_client.hset(
            key, mapping={"artifacts": json.dumps(artifacts), "updated_at": time.time()}
        )

        # Publish Event
        # We need to find the artifact we just added/modified
        target_art = next((a for a in artifacts if a["name"] == name), None)
        if target_art:
            action = "update" if status == "modified" else "create"
            await redis_client.publish(
                f"chat:{thread_id}:events",
                ArtifactEvent(action=action, name=name, data=target_art).json(),
            )

    async def get_activity(self, thread_id: str):
        key = f"activity:{thread_id}"
        data = await redis_client.hgetall(key)
        if not data:
            return {"status": "idle", "tasks": [], "artifacts": []}

        # Parse JSON fields
        try:
            steps = json.loads(data.get("steps", "[]"))
            artifacts = json.loads(data.get("artifacts", "[]"))
            agent_state = json.loads(data.get("agent_state", "{}"))
            verification = json.loads(data.get("verification", "{}"))
            active_memories = json.loads(data.get("active_memories", "[]"))  # Phase 7

            human_request_raw = data.get("human_request")
            human_request = json.loads(human_request_raw) if human_request_raw else None
        except Exception:
            steps = []
            artifacts = []
            agent_state = {}
            verification = {}
            active_memories = []
            human_request = None

        return {
            "status": data.get("status", "unknown"),
            "main_goal": data.get("main_goal", ""),
            "updated_at": float(data.get("updated_at", 0)),
            "steps": steps,
            "artifacts": artifacts,
            "agent_state": agent_state,
            "verification": verification,
            "active_memories": active_memories,  # Phase 7
            "human_request": human_request,
        }

    async def get_statuses(self, thread_ids: list[str]) -> dict[str, str]:
        """Batch fetch statuses for multiple threads efficiently."""
        if not thread_ids:
            return {}

        pipeline = redis_client.pipeline()
        for tid in thread_ids:
            pipeline.hget(f"activity:{tid}", "status")

        results = await pipeline.execute()

        status_map = {}
        for i, status in enumerate(results):
            if status:
                status_map[thread_ids[i]] = status
            else:
                status_map[thread_ids[i]] = "unknown"

        return status_map


# Global Instance
activity_monitor = ActivityMonitor.get_instance()
