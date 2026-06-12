import asyncio
import logging
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, ToolCall
from langgraph.prebuilt import ToolNode
from typing import Dict, Any

from app.domain.tools.execution import execute_command
from app.core.tools.registry import register_tool

register_tool(execute_command)

class DebugCallback(AsyncCallbackHandler):
    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        print("\n=== on_tool_start ===")
        print("serialized:", serialized)
        print("kwargs keys:", kwargs.keys())
        print("kwargs['name']:", kwargs.get("name"))
        print("=====================\n")

async def main():
    print("Testing ToolNode invocation with execute_command")
    
    # LangGraph ToolNode execution
    node = ToolNode([execute_command])
    
    # Simulate an AI message calling the tool
    tool_call = ToolCall(name="execute_command", args={"command": "echo 'Hello World'"}, id="call_12345")
    ai_msg = AIMessage(content="", tool_calls=[tool_call])
    
    # Run ToolNode
    try:
        await node.ainvoke({"messages": [ai_msg]}, config={"callbacks": [DebugCallback()]})
    except Exception as e:
        print(f"Error during ToolNode invocation: {e}")

if __name__ == "__main__":
    asyncio.run(main())
