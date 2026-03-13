import asyncio
import os
import sys
import json

# Fix python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.domain.tools.learning.search_native_tools import search_native_tools

async def test_search_tools():
    # Test listing all tools
    result = await search_native_tools.ainvoke({"query": ""})
    tools = result.get('tools', [])
    print(f"Total tools matched: {result.get('total_tools_matched')}")
    
    names_to_tools = {t['name']: t for t in tools}
    for target in ['browser_control', 'read_file', 'route_to', 'desktop_control']:
        if target in names_to_tools:
            print(f"Tool: {target}, Route To: {names_to_tools[target].get('route_to')}")
        else:
            print(f"Tool: {target} NOT FOUND")

if __name__ == "__main__":
    asyncio.run(test_search_tools())
