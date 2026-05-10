import sys
import os
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

import asyncio
from app.infrastructure.queue.huey_queue import get_huey_scheduler

async def flush_queue():
    try:
        scheduler = get_huey_scheduler()
        huey = scheduler.get_huey()
        print(f"Flushing Huey queue: {scheduler.name}")
        huey.flush()
        print("Queue flushed successfully.")
    except Exception as e:
        print(f"Error flushing queue: {e}")

if __name__ == "__main__":
    asyncio.run(flush_queue())
