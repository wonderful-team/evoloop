import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from app.domain.memory.service import memory_service


async def verify_graph_memory():
    print("🚀 Starting Graph Memory Verification...")

    # 1. Initialize Schema (Indexes)
    print("step 1: initializing schema...")
    await memory_service.initialize_schema()

    project_id = 999 # Test Project
    goal = "Test Goal: Implement Graph Memory Verification"
    result = "Success"
    plan = "- Step 1: Write test script\n- Step 2: Run test"
    error = None

    # 2. Store Episode
    print(f"step 2: storing episode for project {project_id}...")
    await memory_service.store_episode(goal, result, plan, error, project_id)

    # 3. Retrieve Similar Episode
    print("step 3: searching for similar episodes...")
    search_query = "Implement memory verification"
    similar = await memory_service.find_similar_episodes(search_query, project_id)

    print("\n--- Search Results ---")
    print(similar)
    print("----------------------\n")

    if "Test Goal" in similar:
         print("✅ Verification PASSED: Created and retrieved episode successfully.")
    else:
         print("❌ Verification FAILED: Could not find the stored episode.")

if __name__ == "__main__":
    asyncio.run(verify_graph_memory())
