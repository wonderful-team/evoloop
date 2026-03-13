import asyncio
import os
import sys

# Add backend dir to sys.path to resolve 'app' imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.core.brain.tools.retrieval import recall_memory
from app.core.memory import memory_manager

async def test_search():
    print("Testing recall_memory tool...")
    
    # Initialize MemoryManager
    await memory_manager.initialize()
    
    # Test query
    query = "闲鱼爬虫 定时任务 APScheduler"
    print(f"\nQuerying: {query}")
    
    result = await recall_memory(query=query, domain="both")
    print("\nResult:")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_search())
