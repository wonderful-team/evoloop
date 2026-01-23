import sys
import os
import asyncio
import logging
from uuid import uuid4

# Add backend to sys.path
# Add backend to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Import from sibling script
import extract_llm_config

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool

# Configure Logging to see HTTP requests
logging.basicConfig(level=logging.DEBUG)
http_logger = logging.getLogger("httpx")
http_logger.setLevel(logging.DEBUG)
http_logger.propagate = True

@tool
def dummy_tool(arg: str):
    """Dummy tool."""
    return "result"

async def main():
    print("--- Zhipu Protocol Reproduction Script ---")
    
    # 1. Get Config
    config = extract_llm_config.get_llm_config()
    if not config:
        print("Error: No Config found in DB.")
        return

    base_url = config.get("LLM_BASE_URL")
    api_key = config.get("LLM_API_KEY")
    model = config.get("LLM_MODEL")
    
    print(f"Config: BaseURL={base_url}, Model={model}, Key={'*' * 6}")


    # 2. Init LLM
    llm = ChatAnthropic(
        api_key=api_key,
        base_url=base_url,
        model_name=model,
        temperature=0.1,
        streaming=False
    ).bind_tools([dummy_tool])
    
    # 3. Scenario Tests
    
    # Scene A: Mixed Text + Tool Use
    print("\n--- Testing Scenario A: Mixed Text + Tool Use ---")
    tool_id = str(uuid4())
    messages_a = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Call the dummy tool."),
        AIMessage(content="I will call the tool now.", tool_calls=[{"name": "dummy_tool", "args": {"arg": "test"}, "id": tool_id}]),
        ToolMessage(content="Tool executed.", tool_call_id=tool_id)
    ]
    
    try:
        print(f"Sending {len(messages_a)} messages (Mixed)...")
        resp = await llm.ainvoke(messages_a)
        print("✅ Scenario A Success!")
    except Exception as e:
        print(f"❌ Scenario A Failed: {e}")

    # Scene C: Parallel Tool Calls
    print("\n--- Testing Scenario C: Parallel Tool Calls ---")
    id1, id2 = str(uuid4()), str(uuid4())
    messages_c = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Call two tools."),
        AIMessage(content="Calling two tools.", tool_calls=[
            {"name": "dummy_tool", "args": {"arg": "1"}, "id": id1},
            {"name": "dummy_tool", "args": {"arg": "2"}, "id": id2}
        ]),
        ToolMessage(content="Res 1", tool_call_id=id1),
        ToolMessage(content="Res 2", tool_call_id=id2)
    ]
    
    try:
        print(f"Sending {len(messages_c)} messages (Parallel Tools)...")
        resp = await llm.ainvoke(messages_c)
        print("✅ Scenario C Success!")
    except Exception as e:
        print(f"❌ Scenario C Failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
