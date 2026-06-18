import asyncio
import os
from anthropic import AsyncAnthropic

async def main():
    client = AsyncAnthropic(
        api_key="sk-kimi-pZPcvecDfE4oIWQlDxvf5FYShrV7Yx2iSUK9dtoWlYwBWNC3kzVo2WWDdYFwO9j3",
        base_url="https://api.kimi.com/coding/",
    )

    tools = [
        {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    }
                },
                "required": ["location"]
            }
        }
    ]

    print("=== Test 1: tool_choice='auto' ===")
    try:
        response = await client.messages.create(
            model="kimi-k2-thinking-turbo",
            max_tokens=1024,
            messages=[{"role": "user", "content": "What is the weather in Paris?"}],
            tools=tools,
            tool_choice={"type": "auto"}
        )
        print("Success! Auto tool choice is supported.")
        for content in response.content:
            if content.type == "tool_use":
                print(f"Tool Use: {content.name}, input: {content.input}")
    except Exception as e:
        print(f"Error with auto: {e}")

    print("\n=== Test 2: tool_choice={'type': 'any'} ===")
    try:
        response = await client.messages.create(
            model="kimi-k2-thinking-turbo",
            max_tokens=1024,
            messages=[{"role": "user", "content": "What is the weather in Paris?"}],
            tools=tools,
            tool_choice={"type": "any"}
        )
        print("Success! 'any' tool choice is supported.")
    except Exception as e:
        print(f"Error with 'any': {e}")

    print("\n=== Test 3: tool_choice={'type': 'tool', 'name': 'get_weather'} with thinking enabled ===")
    try:
        response = await client.messages.create(
            model="kimi-k2-thinking-turbo",
            max_tokens=4000,
            messages=[{"role": "user", "content": "What is the weather in Paris?"}],
            tools=tools,
            tool_choice={"type": "tool", "name": "get_weather"},
            extra_body={"thinking": {"type": "enabled", "budget_tokens": 1024}}
        )
        print("Success! Specific tool choice is supported.")
    except Exception as e:
        print(f"Error with specific tool: {e}")

if __name__ == "__main__":
    asyncio.run(main())
