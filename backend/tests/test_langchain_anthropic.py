import asyncio
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

class Weather(BaseModel):
    location: str
    temperature: float

async def main():
    llm = ChatAnthropic(
        model_name="kimi-k2-thinking-turbo",
        anthropic_api_url="https://api.kimi.com/coding/",
        anthropic_api_key="sk-kimi-pZPcvecDfE4oIWQlDxvf5FYShrV7Yx2iSUK9dtoWlYwBWNC3kzVo2WWDdYFwO9j3",
    )
    
    structured_llm = llm.with_structured_output(Weather)
    
    print("Testing with_structured_output...")
    try:
        res = await structured_llm.ainvoke("What is the weather in Paris?")
        print("Success:", res)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
