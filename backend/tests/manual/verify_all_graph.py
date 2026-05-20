import asyncio
import logging
import sys
import os
from pathlib import Path

# Add project root and backend root to path
backend_root = Path(__file__).parent.parent.parent
sys.path.append(str(backend_root))

from tests.manual.verify_graph_unified import main as test_memory
from tests.manual.verify_atlas_unified import test_atlas_integration as test_atlas
from tests.manual.verify_service_unified import test_graph_service as test_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FullTest")

async def run_all():
    logger.info("🚀 Starting Full Graph Architecture Test Suite...")
    
    try:
        # 1. Memory & Driver tests
        await test_memory()
        
        # 2. Atlas tests
        await test_atlas()
        
        # 3. Domain Service tests
        await test_service()
        
        logger.info("\n" + "="*50)
        logger.info("🏆 ALL SYSTEMS GO: GRAPH ARCHITECTURE IS STABLE!")
        logger.info("="*50)
    except Exception as e:
        logger.error(f"\n❌ TEST SUITE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_all())
