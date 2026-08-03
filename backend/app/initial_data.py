import asyncio
import logging

from scripts.seed_system_config import init  # noqa: F401

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    from scripts.seed_system_config import main as async_main

    asyncio.run(async_main())
