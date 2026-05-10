import asyncio
import sys
import os
import httpx
from pathlib import Path

# 设置环境
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def audit_token():
    print("=== EvoLoop Token Audit (Advanced) ===")

    try:
        from app.core.identity import identity_service
        from app.infrastructure.cache import cache
        from app.core.config import settings

        # 1. 检测缓存后端
        cache_backend = "FileCache" if settings.EMBEDDED_MODE else "RedisCache"
        print(f"Cache Backend: {cache_backend}")

        # 2. 获取 Token
        token = await identity_service.get_access_token()
        refresh_token = await identity_service.get_refresh_token()

        if not token:
            print("ERROR: No access token found.")
            return

        print(f"Access Token: {token[:10]}...{token[-10:]} (Len: {len(token)})")

        # 3. 执行请求测试
        api_url = str(settings.EVOCLOUD_API_URL).rstrip("/")
        url = f"{api_url}/member/api/member/info"

        print(f"Testing Request: {url}")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"token": token})
            print(f"HTTP Status: {resp.status_code}")
            data = resp.json()
            print(f"API Response: {data}")

            if data.get("code") == 0:
                print("✓ RESULT: Token is VALID")
            elif data.get("code") == -10010:
                print("✗ RESULT: Token EXPIRED (The server rejected it)")
            else:
                print(f"✗ RESULT: Unexpected API Error: {data.get('message')}")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(audit_token())
