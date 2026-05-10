import sys
import os
import asyncio
import logging

# 设置环境
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_recursion():
    print("=== EvoCloudManager Recursion Test ===")
    
    from app.core.evocloud.manager import EvoCloudManager
    from app.core.evocloud.schemas import EvoCloudConfig
    
    manager = EvoCloudManager()
    
    # 构造一个配置
    config = EvoCloudConfig(
        api_url="http://localhost",
        ws_url="ws://localhost",
        app_data_dir="/tmp/evoloop"
    )
    
    print("Accessing manager.api for the first time...")
    try:
        # 这里会触发 initialize()，而 initialize() 内部又调了 self.api
        api_client = manager.api
        print("Success! (If you see this, my recursion theory might be wrong or masked)")
    except RecursionError:
        print("\n[VERIFIED] ✗ RECURSION ERROR DETECTED!")
        print("The lazy initialization in @property api/link causes an infinite loop.")
    except Exception as e:
        print(f"Caught unexpected exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    # 配置日志避免输出干扰
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(test_recursion())
