
import os
try:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage
    print("Success: langchain_anthropic module found and imported.")
except ImportError as e:
    print(f"Error: Failed to import langchain_anthropic. {e}")
    exit(1)

# Configuration mimicking the App Settings
BASE_URL = "https://open.bigmodel.cn/api/anthropic"
API_KEY = "d2033edaf0c1d87b41f42366f7aae4b5.WYlbTIeOTeqltlVt"
MODEL = "glm-4.7"

print(f"Testing ChatAnthropic with Base URL: {BASE_URL}")

try:
    llm = ChatAnthropic(
        api_key=API_KEY,
        base_url=BASE_URL,
        model=MODEL,
        temperature=0.7,
    )

    messages = [HumanMessage(content="Hello, verification test.")]
    
    # We expect a 429/Balance error, which confirms the client worked and reached the server
    print("Sending request...")
    response = llm.invoke(messages)
    print("Response received:")
    print(response.content)

except Exception as e:
    print(f"Caught expected exception or error: {e}")
