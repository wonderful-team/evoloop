import asyncio
import os
import sys

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.infrastructure.llm.factory import LLMFactory
from langchain_core.messages import SystemMessage, HumanMessage

async def main():
    llm = await LLMFactory.create_llm(model_name="kimi-k2-thinking-turbo", temperature=0.1)
    messages = [
        SystemMessage(content="You must output a JSON object: {\"status\": \"ok\"}. Please output the JSON object wrapped inside a markdown json code block."),
        HumanMessage(content="Do it.")
    ]
    res = await llm.ainvoke(messages)
    print("Content:", repr(res.content))
    print("Additional Kwargs:", res.additional_kwargs)

if __name__ == "__main__":
    asyncio.run(main())
