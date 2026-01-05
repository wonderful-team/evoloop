from typing import Dict, List, Any, Optional
import time
import json
import redis.asyncio as redis
import asyncio
from app.core.config import settings

class ActivityMonitor:
    _instance = None
    
    def __init__(self):
        # We use a managed pool from settings? 
        # Or just create a client. Recommendation is one client per app usually.
        self.redis_url = settings.REDIS_URL
        # Map: EventLoop -> RedisClient
        self._clients = {} 
        self._global_client = None
        
    async def get_client(self) -> redis.Redis:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Fallback if called outside loop (unlikely for async methods)
            return redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)

        if loop in self._clients:
             client = self._clients[loop]
             # Check if closed? Redis client doesn't expose is_closed easily, but we trust it.
             return client
             
        # New Client for this loop
        client = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        self._clients[loop] = client
        return client
      
    @property
    def client(self) -> redis.Redis:
         # Deprecated property access, but kept for backward compat if synchronous? 
         # But all usages are `await self.client...` which is wrong if client is property returning object.
         # Actually usages are `await self.client.hset(...)`. 
         # We need to change usages to `client = await self.get_client(); await client.hset(...)` 
         # OR make `client` property return a proxy? 
         # Simpler: The usages are `self.client.hset`. `self.client` returns the Redis object.
         # If I change `client` to a method, I break all calls.
         # BUT `client` property cannot be async.
         # AND `asyncio.get_running_loop()` works inside property if called from async function? Yes.
         
         # Let's try to keep property but make it smart.
         try:
            loop = asyncio.get_running_loop()
            if loop not in self._clients:
                self._clients[loop] = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
            return self._clients[loop]
         except RuntimeError:
             # If no loop running, return a default/global one?
             if self._global_client is None:
                 self._global_client = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
             return self._global_client
        
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
            "tasks": json.dumps([]),     
            "artifacts": json.dumps([]), 
            "updated_at": now
        }
        # Use HSET
        await self.client.hset(key, mapping=data)
        # Expiry 24h
        await self.client.expire(key, 86400)
    
    async def end_run(self, thread_id: str, status="done"):
        key = f"activity:{thread_id}"
        # Check current status first to handle stopping->cancelled
        current_status = await self.client.hget(key, "status")
        
        final_status = status
        if current_status == "stopping":
            final_status = "cancelled"
            
        await self.client.hset(key, mapping={
            "status": final_status,
            "updated_at": time.time()
        })
        
        # Mark running tasks as done/cancelled
        tasks_json = await self.client.hget(key, "tasks")
        if tasks_json:
            tasks = json.loads(tasks_json)
            modified = False
            for t in tasks:
                if t["status"] == "running":
                    t["status"] = "cancelled" if final_status == "cancelled" else "done"
                    modified = True
            if modified:
                 await self.client.hset(key, "tasks", json.dumps(tasks))

    async def stop_run(self, thread_id: str):
        """Signal a run to stop."""
        key = f"activity:{thread_id}"
        if await self.client.exists(key):
            await self.client.hset(key, mapping={
                "status": "stopping",
                "updated_at": time.time()
            })

    async def check_cancellation(self, thread_id: str):
        """Check if run is marked for stopping and raise exception if so."""
        key = f"activity:{thread_id}"
        status = await self.client.hget(key, "status")
        if status == "stopping":
            raise InterruptedError("Cancelled by user")

    
    async def add_task(self, thread_id: str, name: str, task_type="node"):
        key = f"activity:{thread_id}"
        
        # Use a lock to prevent Race Conditions on the JSON list
        lock_key = f"lock:{key}"
        # We need a dedicated client for locking usually, or just use the same one.
        # redis-py lock is robust.
        
        try:
            async with self.client.lock(lock_key, timeout=2.0, blocking_timeout=1.0):
                if not await self.client.exists(key):
                    return None
            
                tasks_json = await self.client.hget(key, "tasks")
                tasks = json.loads(tasks_json) if tasks_json else []
                
                task_id = len(tasks) + 1
                new_task = {
                    "id": task_id,
                    "name": name,
                    "status": "running",
                    "type": task_type,
                    "start_time": time.time(),
                    "time": "0s"
                }
                tasks.append(new_task)
                
                await self.client.hset(key, mapping={
                    "tasks": json.dumps(tasks),
                    "updated_at": time.time()
                })
                return task_id
        except Exception as e:
            # If lock fails, we might just skip adding task to avoid blocking execution?
            # Or retry. For UI visibility, skipping is better than crashing.
            return None

    async def update_task(self, thread_id: str, task_id: int, status: str, details: str = None):
        key = f"activity:{thread_id}"
        lock_key = f"lock:{key}"
        
        try:
            async with self.client.lock(lock_key, timeout=2.0, blocking_timeout=1.0):
                # We need to fetch, modify, save.
                tasks_json = await self.client.hget(key, "tasks")
                if not tasks_json: return
                
                tasks = json.loads(tasks_json)
                modified = False
                
                for task in tasks:
                    if task["id"] == task_id:
                        task["status"] = status
                        if details:
                            task["details"] = details
                        if status in ["done", "failed"]:
                            duration = time.time() - task["start_time"]
                            task["time"] = f"{duration:.2f}s"
                        modified = True
                        break
                
                if modified:
                    await self.client.hset(key, mapping={
                        "tasks": json.dumps(tasks),
                        "updated_at": time.time()
                    })
        except Exception:
            pass

    async def update_agent_state(self, thread_id: str, mode: str, task_name: str, task_status: str):
        # New method to sync Agent State (Sidebar info)
        key = f"activity:{thread_id}"
        state = {
            "mode": mode,
            "task_name": task_name,
            "task_status": task_status
        }
        await self.client.hset(key, "agent_state", json.dumps(state))

    async def add_artifact(self, thread_id: str, name: str, artifact_type: str, status="created", path: str = None):
        key = f"activity:{thread_id}"
        arts_json = await self.client.hget(key, "artifacts")
        artifacts = json.loads(arts_json) if arts_json else []
            
        # Check uniqueness
        for art in artifacts:
            if art["name"] == name:
                art["status"] = "modified"
                await self.client.hset(key, "artifacts", json.dumps(artifacts))
                return
        
        artifacts.append({
            "id": len(artifacts) + 1,
            "name": name,
            "type": artifact_type,
            "status": status,
            "path": path,
            "icon": "FileCode" 
        })
        
        await self.client.hset(key, mapping={
            "artifacts": json.dumps(artifacts),
            "updated_at": time.time()
        })

    async def get_activity(self, thread_id: str):
        key = f"activity:{thread_id}"
        data = await self.client.hgetall(key)
        if not data:
            return {
                "status": "idle",
                "tasks": [],
                "artifacts": []
            }
            
        # Parse JSON fields
        try:
            tasks = json.loads(data.get("tasks", "[]"))
            artifacts = json.loads(data.get("artifacts", "[]"))
            agent_state = json.loads(data.get("agent_state", "{}"))
            verification = json.loads(data.get("verification", "{}"))
        except:
            tasks = []
            artifacts = []
            agent_state = {}
            verification = {}
            
        return {
            "status": data.get("status", "unknown"),
            "main_goal": data.get("main_goal", ""),
            "updated_at": float(data.get("updated_at", 0)),
            "tasks": tasks,
            "artifacts": artifacts,
            "agent_state": agent_state,
            "verification": verification
        }

    async def get_statuses(self, thread_ids: List[str]) -> Dict[str, str]:
        """Batch fetch statuses for multiple threads efficiently."""
        if not thread_ids:
            return {}
            
        pipeline = self.client.pipeline()
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
