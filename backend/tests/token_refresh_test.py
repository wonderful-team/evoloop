import asyncio
import sys
import os
import httpx
import json
from datetime import datetime

# 设置环境
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_refresh_flow():
    print(f"=== EvoLoop Token Refresh Diagnostic ({datetime.now()}) ===")

    from app.core.identity import identity_service
    from app.core.config import settings
    from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
    from app.core.evocloud.schemas import EvoCloudConfig

    # 1. 检查当前状态
    old_token = await identity_service.get_access_token()
    refresh_token = await identity_service.get_refresh_token()

    print(f"Current Access Token (first 15): {old_token[:15] if old_token else 'NONE'}")
    print(f"Current Refresh Token (first 15): {refresh_token[:15] if refresh_token else 'NONE'}")

    # 2. 初始化 API 客户端并尝试刷新
    config = EvoCloudConfig(
        api_url=str(settings.EVOCLOUD_API_URL),
        ws_url=str(settings.EVOCLOUD_WS_URL),
    )
    client = EvoCloudHTTPClient(config)

    print("\n--- Triggering Refresh ---")
    new_token = await client.refresh_access_token()

    if new_token:
        print(f"New Token Received: {new_token[:15]}...")
        if new_token == old_token:
            print("WARNING: New token is IDENTICAL to the old one!")
        else:
            print("✓ SUCCESS: Received a different token.")

        # 3. 验证新 Token 的服务器有效性
        print("\n--- Validating New Token ---")
        api_url = str(settings.EVOCLOUD_API_URL).rstrip("/")
        url = f"{api_url}/member/api/member/info"
        async with httpx.AsyncClient() as h:
            resp = await h.get(url, params={"token": new_token})
            print(f"Server Status: {resp.status_code}")
            data = resp.json()
            print(f"Server Response: {data}")

            if data.get("code") == 0:
                print("✓ RESULT: NEW TOKEN IS VALID!")
            else:
                print(f"✗ RESULT: NEW TOKEN IS STILL EXPIRED/INVALID: {data.get('message')}")

        # 4. 检查持久化是否更新
        print("\n--- Checking Persistence ---")
        # 再次从 identity_service 读取（模拟重新运行）
        stored_token = await identity_service.get_access_token()
        if stored_token == new_token:
            print("✓ CONFIRMED: Identity Service stored the new token.")
        else:
            print(f"✗ FAILED: Stored token ({stored_token[:15] if stored_token else 'NONE'}) does not match new token!")

    else:
        print("✗ FAILED: Token refresh failed completely.")

if __name__ == "__main__":
    asyncio.run(test_refresh_flow())
