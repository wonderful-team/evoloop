import asyncio
import os
import sys

# Add backend dir to sys.path to resolve 'app' imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.infrastructure.llm.factory import LLMFactory
from app.core.evocloud import evocloud_manager
from app.utils.async_utils import flush_loop_bound_resources
from app.domain.tools.environment.browser import browser_manager

async def simulate_celery_task(task_id: int):
    print(f"Task {task_id}: Started in event loop id={id(asyncio.get_running_loop())}")
    
    try:
        # 1. Use LLMFactory
        print(f"Task {task_id}: Testing LLMFactory HTTP client...")
        llm = LLMFactory.create_llm()
        
        # 2. Use EvoCloudManager
        print(f"Task {task_id}: Testing EvoCloud HTTP client...")
        if not evocloud_manager._initialized:
            evocloud_manager.initialize()
        # Access API client properties to trigger instantiation
        _ = await evocloud_manager.api.get_client()
        
        # 3. Use BrowserManager (contains Lock)
        print(f"Task {task_id}: Testing BrowserManager Lock...")
        # Just access the lock via get_page or explicitly
        lock = browser_manager._lock_pool.get()
        async with lock:
            pass
            
    finally:
        print(f"Task {task_id}: Flushing resources...")
        await flush_loop_bound_resources()
        print(f"Task {task_id}: Finished safely.")

if __name__ == "__main__":
    for i in range(3):
        print(f"\n--- Initiating Run {i+1} ---")
        asyncio.run(simulate_celery_task(i+1))

