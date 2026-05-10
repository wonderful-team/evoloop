import json
from dataclasses import dataclass
from typing import Any
from app.core.engine.message.factory import MessageBlockFactory
from app.i18n.service import i18n

@dataclass
class MockMessage:
    id: str
    role: str
    content: str
    thread_id: str = "test-thread"
    status: str = "completed"
    tool_name: str = None
    meta_data: dict = None
    created_at: Any = None

def test_search_summary():
    print("Testing Search Summary Rendering...")
    
    # 1. Simulate search_files output
    tool_output = json.dumps({"content": "Found some files...", "count": 42})
    
    msg = MockMessage(
        id="msg-1",
        role="tool",
        content=tool_output,
        tool_name="search_files",
        meta_data={
            "input": {"pattern": "test_pattern", "path": "src/"}
        }
    )
    
    # 2. Process via factory
    block = MessageBlockFactory.from_orm(msg)
    
    print(f"Tool Name: {block.tool_name}")
    print(f"Status: {block.status}")
    print(f"Display Name: {block.tool_meta['display_name']}")
    
    # Verification
    expected_fragment = "找到 42 个结果"
    if expected_fragment in block.tool_meta['display_name']:
        print("✅ SUCCESS: Count detected and rendered in summary.")
    else:
        print(f"❌ FAILURE: Expected count not found in summary. Got: {block.tool_meta['display_name']}")

    # 3. Test running status (should show original template)
    msg_running = MockMessage(
        id="msg-2",
        role="tool",
        content="",
        status="running",
        tool_name="search_files",
        meta_data={"input": {"pattern": "test_pattern"}}
    )
    block_running = MessageBlockFactory.from_orm(msg_running)
    print(f"Running Display Name: {block_running.tool_meta['display_name']}")
    if "搜索代码" in block_running.tool_meta['display_name']:
         print("✅ SUCCESS: Running status uses call template.")

if __name__ == "__main__":
    test_search_summary()
