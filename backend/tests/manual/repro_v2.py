
import asyncio
import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

from app.core.config import settings

# Configure logging to see the cascading truncation clearly
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

async def main():
    # 1. Tweak settings to induce truncation
    # Force worker to return early
    settings.WORKER_AGENT_MAX_STEPS = 20
    # Keep supervisor limit normal to see its behavior (e.g., 20)
    settings.SUPERVISOR_AGENT_MAX_STEPS = 10 
    
    print(f"DEBUG: WORKER_AGENT_MAX_STEPS = {settings.WORKER_AGENT_MAX_STEPS}")
    print(f"DEBUG: SUPERVISOR_AGENT_MAX_STEPS = {settings.SUPERVISOR_AGENT_MAX_STEPS}")

    # 2. Import and run the lifecycle test
    from tests.manual.test_wiki_generation_lifecycle_v2 import main as wiki_main
    
    # We override sys.argv to pass arguments to the lifecycle test
    sys.argv = [
        sys.argv[0],
        "--budget", "900", # 15 minutes is enough to see a full run
    ]
    
    await wiki_main()

if __name__ == "__main__":
    asyncio.run(main())
