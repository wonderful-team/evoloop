
import asyncio
import os
import sys
from datetime import datetime
from typing import Any, List, Optional
from unittest.mock import MagicMock

# Setup path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.engine.message.mapper import BlockMapper
from app.core.engine.message.schemas import MessageBlock
from langchain_core.messages import AIMessage, ToolMessage

def verify_tool_consistency():
    print("🚀 Verifying Tool Output Consistency...")
    
    thread_id = "thread_abc_123"
    run_id = "run_test_789"
    seq = 2
    tool_call_id = "call_test_123"
    tool_name = "read_file"
    tool_output = "File content: hello world"
    tool_meta = {"display_name": "Read test.txt", "affected_path_keys": ["path"]}

    # 1. SSE Path (using ToolMessage)
    tool_msg = ToolMessage(
        content=tool_output,
        tool_call_id=tool_call_id,
        name=tool_name,
        additional_kwargs={
            "thread_id": thread_id,
            "run_id": run_id,
            "sequence_number": seq,
            "category": "tool_output",
            "tool_meta": tool_meta # DatabaseCallbackHandler often carries this
        }
    )
    
    sse_block = BlockMapper.from_langchain(tool_msg)
    sse_dict = sse_block.model_dump()
    
    # 2. DB Path
    from app.models import Message as DBMessage
    
    mock_db_msg = MagicMock(spec=DBMessage)
    mock_db_msg.thread_id = thread_id
    mock_db_msg.role = "tool"
    mock_db_msg.content = tool_output
    mock_db_msg.tool_calls = None
    mock_db_msg.sequence_number = seq
    mock_db_msg.run_id = run_id
    mock_db_msg.category = "tool_output"
    mock_db_msg.status = "completed"
    mock_db_msg.created_at = datetime.now()
    mock_db_msg.is_visible = True
    mock_db_msg.tool_call_id = tool_call_id
    mock_db_msg.tool_name = tool_name
    mock_db_msg.references = []
    mock_db_msg.content_type = "text"
    mock_db_msg.thinking = ""
    mock_db_msg.parent_id = None
    mock_db_msg.checkpoint_id = ""
    mock_db_msg.meta_data = {
        "tool_meta": tool_meta,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name
    }

    history_block = BlockMapper.from_db(mock_db_msg)
    history_dict = history_block.model_dump()
    
    # 3. Compare
    mismatches = 0
    ignore_keys = {"created_at", "id"} # Skip created_at due to mock timing, skip id if generated differently
    
    for k in sorted(set(sse_dict.keys()) | set(history_dict.keys())):
        if k in ignore_keys: continue
        if sse_dict.get(k) != history_dict.get(k):
            print(f"❌ MISMATCH [{k}]:")
            print(f"   SSE:  {sse_dict.get(k)}")
            print(f"   HIST: {history_dict.get(k)}")
            mismatches += 1

    if mismatches == 0:
        print("✅ Tool Output Aligned!")
        # Check ID specifically since we fixed it
        if sse_dict['id'] == history_dict['id']:
            print(f"✅ ID Aligned: {sse_dict['id']}")
        else:
            print(f"❌ ID MISMATCH: {sse_dict['id']} vs {history_dict['id']}")
            mismatches += 1
    
    return mismatches

if __name__ == "__main__":
    if verify_tool_consistency() == 0:
        print("\n✨ ALL TESTS PASSED!")
    else:
        sys.exit(1)
