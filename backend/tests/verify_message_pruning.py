
import asyncio
import unittest
import sys
import os

# Add app directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from app.core.engine.nodes.supervisor import SupervisorNode
from app.core.engine.nodes.worker import WorkerNode

class TestMessagePruning(unittest.TestCase):
    def setUp(self):
        # 构造一个模拟的长对话历史
        self.messages = [
            SystemMessage(content="system instructions"),
            HumanMessage(content="Help me write a file."),
            HumanMessage(content="telemetry data 1", name="context_ticket"),
            AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"path": "a.txt"}, "id": "1"}]),
            ToolMessage(content="file content...", tool_call_id="1"),
            AIMessage(content="I've read the file. Now I will write it.", tool_calls=[{"name": "write_file", "args": {}, "id": "2"}]),
            ToolMessage(content="success", tool_call_id="2"),
            AIMessage(content="Worker: I have finished the subtask 1."),
            HumanMessage(content="telemetry data 2", name="context_ticket"),
            AIMessage(content="", tool_calls=[{"name": "search_files", "args": {"query": "test"}, "id": "3"}]),
            ToolMessage(content="found test.py", tool_call_id="3"),
            AIMessage(content="Worker: I have finished the entire task."),
            HumanMessage(content="latest telemetry", name="context_ticket"),
        ]

    def test_supervisor_filtering(self):
        """验证 Supervisor 是否完全去掉了工具链，只保留语义层结果"""
        print("\n[Test] Testing Supervisor Filtering...")
        filtered = SupervisorNode._filter_messages_for_supervisor(self.messages)
        
        # 验证: 不应该存在 ToolMessage 和带 tool_calls 的 AIMessage
        self.assertFalse(any(isinstance(m, ToolMessage) for m in filtered), "Supervisor should not see ToolMessages")
        self.assertFalse(any(isinstance(m, AIMessage) and m.tool_calls for m in filtered), "Supervisor should not see AIMessages with tool_calls")
        
        # 验证: 应该保留最新的 context_ticket 和总结性 AIMessage
        has_summary = any(isinstance(m, AIMessage) and "Worker: I have finished the entire task" in m.content for m in filtered)
        self.assertTrue(has_summary, "Supervisor should see Worker's final summary")
        
        # 验证: 只保留一个最新的 context_ticket
        ticket_count = sum(1 for m in filtered if isinstance(m, HumanMessage) and m.name == "context_ticket")
        self.assertEqual(ticket_count, 1, f"Supervisor should see exactly 1 context_ticket, found {ticket_count}")
        
        # 验证: 原始 HumanMessage 必须保留
        self.assertTrue(any(isinstance(m, HumanMessage) and not m.name for m in filtered), "Supervisor should see original HumanMessage")
        
        print(f"Supervisor Filtered: {len(self.messages)} -> {len(filtered)} msgs (Success)")

    def test_worker_isolation(self):
        """验证 Worker 是否只保留原始需求，隔离历史执行过程"""
        print("\n[Test] Testing Worker Isolation...")
        filtered = WorkerNode._build_worker_view(self.messages)
        
        # 验证: 应该丢弃所有之前的 AI、Tool 和 注入的人类消息(ticket)
        self.assertFalse(any(isinstance(m, AIMessage) for m in filtered), "Worker should not see previous AIMessages")
        self.assertFalse(any(isinstance(m, ToolMessage) for m in filtered), "Worker should not see previous ToolMessages")
        self.assertFalse(any(isinstance(m, HumanMessage) and m.name == "context_ticket" for m in filtered), "Worker should not see previous context_tickets")
        
        # 验证: 应该保留 System 和 原始 Human
        self.assertTrue(any(isinstance(m, SystemMessage) for m in filtered), "Worker must see SystemMessage")
        self.assertTrue(any("Help me write a file" in m.content for m in filtered if isinstance(m, HumanMessage)), "Worker must see original request")
        
        print(f"Worker View: {len(self.messages)} -> {len(filtered)} msgs (Success)")

if __name__ == "__main__":
    unittest.main()
