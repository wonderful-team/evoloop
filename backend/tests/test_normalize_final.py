import asyncio
import json
from app.core.engine.message.folder import MessageNormalizer
from app.core.engine.message.repository import MessageRepository

async def test():
    thread_id = "383918d5-3b6a-433b-8813-79a6f1625860"
    repo = MessageRepository(thread_id=thread_id)
    
    # 1. Get raw messages from DB
    all_messages, _, _ = await repo.get_full_history(limit=30)
    print(f"Total raw messages from DB: {len(all_messages)}")
    
    # 2. Normalize directly
    normalized = MessageNormalizer.normalize(all_messages)
    print(f"Total normalized messages: {len(normalized)}")
    
    # 3. Check for route_to
    has_route_to = any(m.metadata.get("tool_name") == "route_to" for m in normalized if m.role == "tool")
    print(f"Has route_to in normalized result: {has_route_to}")
    
    # Print the first few tool messages for inspection
    for m in normalized:
        if m.role == "tool":
            print(f"Tool Message: {m.metadata.get('tool_name')} - Hidden in Registry: {getattr(m, 'is_hidden', 'N/A')}")

if __name__ == "__main__":
    asyncio.run(test())
