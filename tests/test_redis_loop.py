import asyncio
import os
import sys

# Add backend dir to sys.path to resolve 'app' imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.infrastructure.database.redis import redis_client
from app.utils.async_utils import flush_loop_bound_resources

async def test_redis(task_id: int):
    print(f"Task {task_id}: Started in event loop id={id(asyncio.get_running_loop())}")
    
    try:
        # 1. Use Redis Proxy
        print(f"Task {task_id}: Testing Redis Proxy...")
        await redis_client.set("test_loop_key", f"test_loop_val_{task_id}", ex=10)
        val = await redis_client.get("test_loop_key")
        print(f"Task {task_id}: Redis returned {val}")
            
    finally:
        print(f"Task {task_id}: Flushing resources...")
        await flush_loop_bound_resources()
        print(f"Task {task_id}: Finished safely.")

if __name__ == "__main__":
    for i in range(3):
        print(f"\n--- Initiating Run {i+1} ---")
        asyncio.run(test_redis(i+1))
