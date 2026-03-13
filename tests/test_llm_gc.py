import asyncio
import gc
import httpx
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

async def test_llm_gc():
    client = httpx.AsyncClient()
    llm = ChatOpenAI(api_key="sk-test", http_async_client=client)
    
    del llm
    gc.collect()
    
    # Let event loop run to see if any task is spawned
    await asyncio.sleep(0.5)
    print(f"Client is closed: {client.is_closed}")
    await client.aclose()

asyncio.run(test_llm_gc())
