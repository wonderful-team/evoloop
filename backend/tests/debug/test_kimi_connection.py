import asyncio
import os
import sys

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(backend_dir)

from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.config.service import SystemConfigService

async def main():
    print("Initializing DB...")
    await db_resource_manager.initialize()
    print("Listing all system configurations in DB:")
    configs = SystemConfigService.get_all()
    for c in configs:
        print(f"{c.key} = {repr(c.value)}")

if __name__ == "__main__":
    asyncio.run(main())
