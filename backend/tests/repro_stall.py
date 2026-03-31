import asyncio
import time
import logging
from app.core.monitoring.activity import activity_monitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_stall_tolerance():
    thread_id = "test-stall-perf"
    await activity_monitor.start_run(thread_id, "Testing stall tolerance")
    
    # Add a step and set it to running
    step_id = await activity_monitor.add_step(thread_id, "Executing huge bash command", "tool")
    await activity_monitor.update_step(thread_id, step_id, "running", details="..." * 1000)
    
    logger.info("Step started and marked as 'running'. Sleeping 40 seconds to simulate long task...")
    
    # This simulation doesn't run the actual monitor from test_with_scenarios.py,
    # but we can see if the status is correctly set.
    
    # Let's see how long a massive update takes in the real monitor context
    huge_payload = "A" * (1024 * 1024) # 1MB
    
    start = time.time()
    for i in range(10): # Simulate 10 token updates
        await activity_monitor.update_step(thread_id, step_id, "running", details=huge_payload[:1000+i])
    end = time.time()
    
    logger.info(f"10 updates with huge steps list took: {(end-start)*1000:.2f}ms")
    
    await activity_monitor.end_run(thread_id)

if __name__ == "__main__":
    asyncio.run(test_stall_tolerance())
