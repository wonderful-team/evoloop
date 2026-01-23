import asyncio
import os
import sys

# Add app to path
sys.path.append(os.path.join(os.getcwd(), "app"))

async def check_status():
    try:
        from app.core.config import settings
        from app.infrastructure.external.evocloud import evocloud_client
        import redis.asyncio as redis

        print(f"EVOCLOUD_API_URL: {settings.EVOCLOUD_API_URL}")
        
        # Check Redis token
        token = None
        try:
            redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            async with redis_client:
                token = await redis_client.get("evoloop:link:token")
                print(f"Redis Token found: {bool(token)}")
        except Exception as e:
            print(f"Redis Error: {e}")

        # Check Client Status
        print(f"Client Token: {bool(evocloud_client.api.get_token())}")
        print(f"Device ID: {evocloud_client.link.device_id}")
        print(f"Is Linked: {evocloud_client.link.is_connected()}")

    except Exception as e:
        print(f"Diagnostic failed: {e}")

if __name__ == "__main__":
    asyncio.run(check_status())
