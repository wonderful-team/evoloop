import sys
import os
import asyncio
import logging

# 设置环境
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 计数器用于记录初始化次数
init_count = 0

async def test_concurrent_init():
    print("=== EvoCloudManager Concurrent Initialization Test ===")
    
    from app.core.evocloud.manager import EvoCloudManager
    from app.core.evocloud.schemas import EvoCloudConfig
    
    manager = EvoCloudManager()
    
    # 装饰 initialize 来计数
    original_init = manager.initialize
    def patched_init(*args, **kwargs):
        global init_count
        init_count += 1
        return original_init(*args, **kwargs)
    manager.initialize = patched_init
    
    config = EvoCloudConfig(
        api_url="http://localhost",
        ws_url="ws://localhost",
        app_data_dir="/tmp/evoloop"
    )

    # 模拟并发访问
    async def access_api():
        # 故意不传 config，让它走内部的懒加载逻辑
        return manager.api

    print("Triggering 10 concurrent API accesses...")
    await asyncio.gather(*[access_api() for _ in range(10)])
    
    print(f"Total initialize() calls: {init_count}")
    
    if init_count > 1:
        print("\n[VERIFIED] ✗ CONCURRENCY ISSUE DETECTED!")
        print(f"initialize() was called {init_count} times. This can cause resource leaks.")
    else:
        print("\n[CONCLUSION] initialize() was called once. Seems safe for current sync execution.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(test_concurrent_init())
