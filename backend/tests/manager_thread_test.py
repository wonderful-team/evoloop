import sys
import os
import asyncio
import threading
import logging

# 设置环境
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def thread_worker(manager):
    print(f"[Thread] Attempting to access manager.api from {threading.current_thread().name}...")
    try:
        # 在非事件循环线程访问
        api = manager.api
        print(f"[Thread] Success! Got api: {api}")
    except Exception as e:
        print(f"[Thread] ✗ FAILED: {type(e).__name__}: {e}")

async def test_threading():
    print("=== EvoCloudManager Threading Test ===")
    
    from app.core.evocloud.manager import EvoCloudManager
    from app.core.evocloud.schemas import EvoCloudConfig
    
    manager = EvoCloudManager()
    config = EvoCloudConfig(
        api_url="http://localhost",
        ws_url="ws://localhost",
        app_data_dir="/tmp/evoloop"
    )
    manager.initialize(config)
    
    # 开启一个后台线程
    t = threading.Thread(target=thread_worker, args=(manager,), name="WorkerThread")
    t.start()
    t.join()

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(test_threading())
