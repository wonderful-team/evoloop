import asyncio
import logging
import sys
import os

from app.domain.tools.learning.list_skills import list_skills
from app.domain.tools.learning.read_skill_sop import read_skill_sop

logging.basicConfig(level=logging.INFO)

async def test_skills():
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize()
    
    print("=== Testing list_skills ===")
    try:
        # Actually list_skills is a StructuredTool instance, so we can call it using invoke or ainvoke
        result = await list_skills.ainvoke({"namespace": None, "query": None})
        print(f"Result (All):\n{result}\n")
    except Exception as e:
        print(f"Failed to list_skills (All): {e}")

    try:
        result = await list_skills.ainvoke({"namespace": "os/android", "query": None})
        print(f"Result (Android namespace):\n{result}\n")
    except Exception as e:
        print(f"Failed to list_skills (Android): {e}")

    print("=== Testing read_skill_sop ===")
    try:
        # We need a valid skill_id to test this properly, or test the error handling
        result = await read_skill_sop.ainvoke({"skill_id": 41})
        print(f"Result (non existent skill):\n{result}\n")
    except Exception as e:
        print(f"Failed to read_skill_sop: {e}")

if __name__ == "__main__":
    # Ensure app imports work correctly
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(test_skills())
