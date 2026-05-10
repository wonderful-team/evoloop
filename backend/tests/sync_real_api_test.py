import asyncio
import sys
import os
import logging
import json
import time

# 设置环境
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_real_api_sync():
    print("=== EvoCloud Real API Sync Test ===")
    
    from app.core.evocloud.manager import evocloud_manager
    from app.core.evocloud.schemas import EvoCloudConfig
    from app.utils.id import gen_uuid
    from app.core.config import settings
    
    # 1. 初始化
    config = EvoCloudConfig(
        api_url=str(settings.EVOCLOUD_API_URL),
        ws_url=str(settings.EVOCLOUD_WS_URL),
        app_data_dir=settings.APP_DATA_DIR
    )
    evocloud_manager.initialize(config)
    api = evocloud_manager.api
    device_key = await evocloud_manager.link.ensure_device_key() or "test_device_key"
    
    # 2. 构造数据 (固定 ID 以测试重复同步)
    thread_id = "test_idempotency_check"
    test_conv = {
        "id": thread_id,
        "project_id": 1,
        "title": "测试同步会话",
        "created_at": int(time.time()),
        "updated_at": int(time.time())
    }
    test_messages = [{
        "id": gen_uuid(),
        "role": "user",
        "content": "这是一条来自测试脚本的模拟同步消息。",
        "thinking": "正在进行全链路测试...",
        "sequence_number": 1,
        "created_at": int(time.time())
    }]
    
    # 3. 执行同步
    try:
        print(f"1. Syncing conversation metadata: {thread_id}...")
        conv_res = await api.sync_conversation(device_key, test_conv)
        print(f"   Response: {conv_res.get('message')}")
        
        if conv_res.get("code") == 0:
            print(f"2. Syncing 1 message for thread: {thread_id}...")
            res = await api.sync_messages(device_key, thread_id, test_messages)
            print("\n--- Final API Response ---")
            print(json.dumps(res, indent=2, ensure_ascii=False))
            
            if res.get("code") == 0:
                print("\n[SUCCESS] Full sync chain completed successfully!")
            else:
                print(f"\n[FAILED] Message sync failed: {res.get('message')}")
        else:
            print(f"\n[FAILED] Conversation sync failed: {conv_res.get('message')}")
            
    except Exception as e:
        print(f"\n[ERROR] Request exception: {e}")

if __name__ == "__main__":
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(test_real_api_sync())
