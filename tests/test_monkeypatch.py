import asyncio
import gc
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from app.infrastructure.llm.factory import LLMFactory

async def _main():
    llm = LLMFactory.create_llm(temperature=0.3)
    # Return it to be garbage collected outside the event loop
    return llm

def test_suppression():
    print("Testing suppression...")
    llm = asyncio.run(_main())
    
    del llm
    gc.collect()
    print("Finished. If no 'Event loop is closed' unretrieved task error follows, the patch works.")

if __name__ == "__main__":
    test_suppression()
