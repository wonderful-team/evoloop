import asyncio
import gc
from langchain_anthropic import ChatAnthropic

async def test_llm_gc():
    llm = ChatAnthropic(api_key="sk-test", model_name="claude-3")
    
    del llm
    gc.collect()
    
    # Let event loop run to see if any task is spawned
    for _ in range(5):
        await asyncio.sleep(0.1)
    
asyncio.run(test_llm_gc())
