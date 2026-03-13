import asyncio
import gc
from langchain_anthropic import ChatAnthropic

async def _main():
    llm = ChatAnthropic(api_key="sk-test", model_name="claude-3")
    # intentionally do NOT delete it here, let Python GC clean it up AFTER loop closes OR while loop closes.
    return llm

def run():
    llm = asyncio.run(_main())
    # Loop is now closed. 
    # Now GC it
    del llm
    gc.collect()

run()
