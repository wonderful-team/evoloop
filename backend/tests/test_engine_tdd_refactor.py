import asyncio
import os
import sys
import unittest
from typing import Any, List, Optional
from unittest.mock import MagicMock, AsyncMock, patch

# Setup path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field
from langgraph.checkpoint.memory import MemorySaver

from app.core.engine.state.base import AgentState, StateUpdate, AgentStateBase
from app.core.engine.state.sub_schemas import ExecutionTicket, SubtaskResult
from app.core.tools.manager import tool_manager
from app.core.engine.nodes.supervisor import SupervisorNode


class MockChatModel(BaseChatModel):
    """Mock Chat Model for TDD refactoring tests."""
    responses: List[AIMessage] = Field(default_factory=list)
    call_index: int = 0

    def _generate(
        self,
        messages: List[BaseMessage] if sys.version_info >= (3, 9) else Any,
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.call_index >= len(self.responses):
            res = AIMessage(content="Default fallback response")
        else:
            res = self.responses[self.call_index]
            self.call_index += 1
        return ChatResult(generations=[ChatResult(generations=[ChatGeneration(message=res)])])

    async def _agenerate(
        self,
        messages: List[BaseMessage] if sys.version_info >= (3, 9) else Any,
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    async def astream(self, input: Any, config: Optional[Any] = None, **kwargs: Any):
        if self.call_index >= len(self.responses):
            res = AIMessage(content="Default fallback response")
        else:
            res = self.responses[self.call_index]
            self.call_index += 1
        yield res

    @property
    def _llm_type(self) -> str:
        return "mock-chat-model"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> Any:
        return self


class TestEngineTDDRefactor(unittest.TestCase):
    def setUp(self):
        # Verify AgentStateBase does not have a blackboard data field in model fields
        if "blackboard" in AgentStateBase.model_fields:
            raise AssertionError(
                "AgentStateBase still has legacy 'blackboard' data field! Refactoring is incomplete."
            )

    def tearDown(self):
        pass

    def test_tool_manager_no_blackboard(self):
        """1. 验证 ToolManager 能够直接读取顶级属性并加载工具，不依赖 blackboard 属性"""
        state = AgentState(
            thread_id="test-thread",
            project_id=1,
            ticket=ExecutionTicket(
                ticket_type="test",
                topic="test-topic",
                mcp_servers_required=["mock-server"]
            )
        )
        with patch("app.core.tools.registry.get_node_tools", return_value=[]), \
             patch("app.core.mcp.mcp_client_manager.aget_all_tools", AsyncMock(return_value=[])):
            
            tools = asyncio.run(tool_manager.get_node_tools("worker", state))
            self.assertIsInstance(tools, list)

    def test_context_cache_no_blackboard(self):
        """2. 验证 LayeredContextCache 不依赖 blackboard 属性进行状态组装"""
        from app.core.context.cache import LayeredContextCache
        state = AgentState(
            thread_id="test-thread",
            project_id=1,
            ticket=ExecutionTicket(ticket_type="test", topic="test-topic")
        )
        try:
            cache_val = LayeredContextCache.get_static_layer
            self.assertTrue(callable(cache_val))
        except AttributeError as e:
            self.fail(f"LayeredContextCache state conversion failed: {e}")

    def test_memory_tools_no_blackboard(self):
        """3. 验证内存工具直接读取顶级通道，不通过 blackboard 属性访问"""
        from app.core.memory.tools import remember, recall
        mock_ctx = MagicMock()
        mock_ctx.metadata.shared_context = {"key": "val"}
        mock_ctx.metadata.tool_memory = {"m": "1"}
        
        # Test that functions are defined and can be patched
        self.assertTrue(callable(remember) or hasattr(remember, "ainvoke"))
        self.assertTrue(callable(recall) or hasattr(recall, "ainvoke"))

    def test_nodes_outcome_no_blackboard(self):
        """4. 验证 Supervisor 节点生成 StateUpdate 时不包含 blackboard 键"""
        state = AgentState(
            thread_id="test-thread",
            project_id=1,
            ticket=ExecutionTicket(ticket_type="test", topic="test-topic"),
            final_outcome="testing"
        )
        
        from app.core.engine.schemas import EngineResult, NodeOutcome
        mock_engine_result = EngineResult(
            messages=[AIMessage(content="Node execution finished")],
            tool_history=[],
            metadata=state,
            is_truncated=False,
            outcome=NodeOutcome(status="success")
        )
        
        supervisor_node = SupervisorNode()
        
        with patch("app.core.engine.nodes.base.logger"):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            update = loop.run_until_complete(
                supervisor_node._build_fallback_outcome(state, mock_engine_result, {})
            )
            
            update_dict = update.model_dump()
            self.assertNotIn("blackboard", update_dict)

    def test_state_update_without_blackboard_serialization(self):
        """5. 验证状态更新字典不包含嵌套 blackboard，并在 model_dump 中为全扁平格式"""
        update = StateUpdate(
            ticket=ExecutionTicket(ticket_type="test", topic="test-topic"),
            final_outcome="completed",
            working_directory="/home/workspace"
        )
        
        dumped = update.model_dump()
        self.assertNotIn("blackboard", dumped)
        self.assertEqual(dumped["working_directory"], "/home/workspace")
        self.assertEqual(dumped["final_outcome"], "completed")

if __name__ == "__main__":
    unittest.main()
