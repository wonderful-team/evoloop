import asyncio
import logging
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.atlas.engine import AtlasEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting Atlas Data Purge (SQL)...")
    try:
        engine = AtlasEngine()
        await engine.clear_atlas()
        logger.info("Purge complete. Atlas data cleared from SQL.")
    except Exception as e:
        logger.error(f"Failed to clear atlas: {e}")

if __name__ == "__main__":
    asyncio.run(main())
