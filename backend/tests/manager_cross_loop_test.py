import sys
import os
import asyncio
import logging

# 设置环境
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_in_new_loop(manager, loop_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def task():
        print(f"\n[Loop {loop_id}] Current Loop ID: {id(asyncio.get_running_loop())}")
        link = manager.link
        api = manager.api
        print(f"[Loop {loop_id}] Manager Link ID: {id(link)}")
        print(f"[Loop {loop_id}] Manager API ID: {id(api)}")
        
        internal_api = link.api
        print(f"[Loop {loop_id}] Link's Internal API ID: {id(internal_api)}")
        
        if id(internal_api) != id(api):
            print(f"[Loop {loop_id}] ✗ WARNING: Link is using a FOREIGN API client!")
        else:
            print(f"[Loop {loop_id}] ✓ Link is using the correct local API client.")
            
    try:
        loop.run_until_complete(task())
    finally:
        loop.close()

def test_real_cross_loop():
    print("=== EvoCloudManager REAL Cross-Loop Pollution Test ===")
    
    from app.core.evocloud.manager import EvoCloudManager
    from app.core.evocloud.schemas import EvoCloudConfig
    
    manager = EvoCloudManager()
    config = EvoCloudConfig(
        api_url="http://localhost",
        ws_url="ws://localhost",
        app_data_dir="/tmp/evoloop"
    )
    # 不在这里显式 initialize，让属性去触发
    
    print("\n--- Running in Loop A ---")
    run_in_new_loop(manager, "A")
    
    print("\n--- Running in Loop B ---")
    run_in_new_loop(manager, "B")

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    test_real_cross_loop()
