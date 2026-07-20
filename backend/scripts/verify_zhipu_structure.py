
import os
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

# Configuration from previous working test
BASE_URL = "https://open.bigmodel.cn/api/anthropic"
API_KEY = "d2033edaf0c1d87b41f42366f7aae4b5.WYlbTIeOTeqltlVt"
MODEL = "glm-4.7"

print(f"Testing ChatAnthropic with Base URL: {BASE_URL}")

try:
    llm = ChatAnthropic(
        api_key=API_KEY,
        base_url=BASE_URL,
        model=MODEL,
        temperature=0.1,
        streaming=False 
    )

    print("--- Test 1: System + Human (Passed before) ---")
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Hello, is the system prompt working?")
    ]
    
    # Test 2: With Tools Bound (Force Call)
    print("\n--- Test 2: With Tools Bound (Forced) ---")
    from langchain_core.tools import tool
    
    @tool
    def search(query: str):
        """Search google."""
        return "result"

    llm_with_tools = llm.bind_tools([search])
    try:
        # Prompt explicitly to use the tool
        msgs = [HumanMessage(content="Use the search tool to look for 'LangChain'.")]
        response = llm_with_tools.invoke(msgs)
        print("Response (With Tools):")
        print(f"Content: {response.content}")
        print(f"Tool Calls: {response.tool_calls}")
    except Exception as e:
        print(f"FAILED (With Tools): {e}")

    # Test 3: Only System Message
    print("\n--- Test 3: Only System Message ---")
    try:
        response = llm.invoke([SystemMessage(content="Just a system message.")])
        print("Response (Only System):")
        print(response.content)
    except Exception as e:
        print(f"FAILED (Only System): {e}")
    
except Exception as e:
    print(f"FAILED: {e}")
