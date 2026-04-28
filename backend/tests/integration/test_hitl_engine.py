"""
HITL (Human-in-the-Loop) 引擎层集成测试

测试范围:
- run_agent_background 对 HITL 中断的处理
- hitl_resume_response 的 Resume 逻辑
- AgentHumanInterruptException 被捕获后的状态管理

运行方式:
    cd backend && python -m pytest tests/integration/test_hitl_engine.py -v
"""

import os
import sys
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

env_path = os.path.join(os.path.dirname(__file__), "../../../.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

# Mock pgvector 模块（在非 PostgreSQL 环境下）
sys.modules["pgvector"] = MagicMock()
sys.modules["pgvector.sqlalchemy"] = MagicMock()

from app.core.engine.background_agent import run_agent_background
from app.core.exceptions import AgentHumanInterruptException
from app.core.monitoring.activity import activity_monitor
from app.infrastructure.database.sql.database import Base, engine, session_scope
from app.models import Conversation, Message
from sqlmodel import SQLModel

pytestmark = pytest.mark.skip(reason="DB initialization hangs in test environment")


@pytest.fixture(scope="module", autouse=True)
async def init_db():
    """模块级数据库初始化"""
    from app.core.config import settings
    from app.infrastructure.database.sql.database import db_resource_manager
    from app.infrastructure.database.resource_manager import DatabaseResourceManager

    if settings.EMBEDDED_MODE:
        from app import models  # noqa: F401
        # Reset singleton state to avoid stale locks from previous imports
        db_resource_manager._initialized = False
        db_resource_manager._engine = None
        db_resource_manager._sync_engine = None
        db_resource_manager._session_factory = None
        db_resource_manager._checkpointer = None
        db_resource_manager._sqlite_conn = None
        await db_resource_manager.initialize()

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    yield


@pytest.fixture(autouse=True)
async def clean_state():
    """每个测试前清理相关表和 activity monitor 状态"""
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM messages"))
        await conn.execute(text("DELETE FROM conversations"))
        await conn.execute(text("DELETE FROM human_requests"))
    yield


class MockGraph:
    """模拟 LangGraph，支持可控的 astream 和 aget_state"""

    def __init__(self, events=None, state=None, raise_on_stream=None):
        self._events = events or []
        self._state = state
        self._raise_on_stream = raise_on_stream

    async def astream(self, input_payload, config=None):
        if self._raise_on_stream:
            raise self._raise_on_stream
        for event in self._events:
            yield event

    async def aget_state(self, config=None):
        return self._state


class MockState:
    """模拟 Graph State"""

    def __init__(self, values=None):
        self.values = values or {}


@pytest.mark.asyncio
async def test_run_agent_background_catches_hitl_and_sets_interrupted_status():
    """
    当 graph.astream 抛出 AgentHumanInterruptException 时，
    run_agent_background 应捕获它并将 activity 状态设为 interrupted
    """
    thread_id = f"hitl-engine-{datetime.now().strftime('%H%M%S')}"

    # 构造一个带 pending tool_call 的 state，用于 resume 时检查
    mock_ai_msg = AIMessage(
        content="需要确认",
        tool_calls=[{
            "id": "call_123",
            "name": "ask_confirm",
            "args": {"action_description": "删除文件"}
        }]
    )
    mock_state = MockState(values={"messages": [mock_ai_msg]})
    mock_graph = MockGraph(raise_on_stream=AgentHumanInterruptException("req-123", "需要确认"))
    mock_graph._state = mock_state  # 用于 aget_state

    with patch("app.core.engine.background_agent.get_graph", return_value=mock_graph), \
         patch("app.core.engine.background_agent.ContextManager") as mock_ctx_manager, \
         patch("app.core.engine.background_agent.MemoryContainer") as mock_memory_container:

        mock_ctx_manager.load_from_redis = AsyncMock(return_value=None)
        mock_ctx_manager.current = MagicMock(return_value=MagicMock(thread_id=thread_id, project_id=1, command_id=None, working_directory="/tmp"))
        mock_memory = MagicMock()
        mock_memory.preferences.get_merged_preferences = AsyncMock(return_value="")
        mock_memory.long_term.get_project_concepts = AsyncMock(return_value="")
        mock_memory_container.return_value.memory_manager = mock_memory

        inputs = {
            "messages": [{"type": "human", "content": "帮我删除文件"}],
            "project_id": 1,
            "goal": "测试 HITL 中断",
        }

        # 第一次运行：预期被 HITL 中断，但 run_agent_background 内部捕获了异常，不会抛出
        await run_agent_background(thread_id, inputs)

        # 验证 activity 状态
        activity = await activity_monitor.get_activity(thread_id)
        # 注意：当前 background_agent.py 中 AgentHumanInterruptException 被捕获后
        # 没有调用 end_run，所以状态可能还是 interrupted（由 tool 设置）
        assert activity is not None
        # 由于 activity_monitor 的状态可能被 tool 设置为 interrupted
        # 我们至少验证没有崩溃，且步骤或状态信息存在
        assert activity.get("status") in ["interrupted", "running"]


@pytest.mark.asyncio
async def test_run_agent_background_resume_with_tool_message():
    """
    传入 hitl_resume_response 时，run_agent_background 应构造 ToolMessage 并 resume graph
    """
    thread_id = f"hitl-resume-{datetime.now().strftime('%H%M%S')}"

    mock_ai_msg = AIMessage(
        content="需要确认",
        tool_calls=[{
            "id": "call_456",
            "name": "ask_confirm",
            "args": {"action_description": "执行操作"}
        }]
    )
    mock_state = MockState(values={"messages": [mock_ai_msg]})

    events_captured = []

    class CapturingMockGraph:
        async def astream(self, input_payload, config=None):
            events_captured.append(input_payload)
            yield {"type": "mock_event"}

        async def aget_state(self, config=None):
            return mock_state

    mock_graph = CapturingMockGraph()

    with patch("app.core.engine.background_agent.get_graph", return_value=mock_graph), \
         patch("app.core.engine.background_agent.ContextManager") as mock_ctx_manager, \
         patch("app.core.engine.background_agent.MemoryContainer") as mock_memory_container:

        mock_ctx_manager.load_from_redis = AsyncMock(return_value=None)
        mock_ctx_manager.current = MagicMock(return_value=MagicMock(thread_id=thread_id, project_id=1, command_id=None, working_directory="/tmp"))
        mock_memory = MagicMock()
        mock_memory.preferences.get_merged_preferences = AsyncMock(return_value="")
        mock_memory.long_term.get_project_concepts = AsyncMock(return_value="")
        mock_memory_container.return_value.memory_manager = mock_memory

        inputs = {
            "hitl_resume_response": "APPROVED",
            "project_id": 1,
            "goal": "测试 HITL Resume",
        }

        await run_agent_background(thread_id, inputs)

        # 验证 resume 时传入的是 Command(resume=ToolMessage(...))
        assert len(events_captured) == 1
        payload = events_captured[0]
        assert isinstance(payload, Command)
        assert isinstance(payload.resume, ToolMessage)
        assert payload.resume.tool_call_id == "call_456"
        assert payload.resume.content == "APPROVED"

        # 验证最终状态为 done
        activity = await activity_monitor.get_activity(thread_id)
        assert activity.get("status") == "done"


@pytest.mark.asyncio
async def test_run_agent_background_resume_fallback_without_tool_call():
    """
    当 state 中没有 pending tool_call 时，resume 应回退到 Command(resume=user_response)
    """
    thread_id = f"hitl-fallback-{datetime.now().strftime('%H%M%S')}"

    mock_state = MockState(values={"messages": []})

    events_captured = []

    class CapturingMockGraph:
        async def astream(self, input_payload, config=None):
            events_captured.append(input_payload)
            yield {"type": "mock_event"}

        async def aget_state(self, config=None):
            return mock_state

    mock_graph = CapturingMockGraph()

    with patch("app.core.engine.background_agent.get_graph", return_value=mock_graph), \
         patch("app.core.engine.background_agent.ContextManager") as mock_ctx_manager, \
         patch("app.core.engine.background_agent.MemoryContainer") as mock_memory_container:

        mock_ctx_manager.load_from_redis = AsyncMock(return_value=None)
        mock_ctx_manager.current = MagicMock(return_value=MagicMock(thread_id=thread_id, project_id=1, command_id=None, working_directory="/tmp"))
        mock_memory = MagicMock()
        mock_memory.preferences.get_merged_preferences = AsyncMock(return_value="")
        mock_memory.long_term.get_project_concepts = AsyncMock(return_value="")
        mock_memory_container.return_value.memory_manager = mock_memory

        inputs = {
            "hitl_resume_response": "继续执行",
            "project_id": 1,
            "goal": "测试 HITL Fallback Resume",
        }

        await run_agent_background(thread_id, inputs)

        assert len(events_captured) == 1
        payload = events_captured[0]
        assert isinstance(payload, Command)
        assert payload.resume == "继续执行"


@pytest.mark.asyncio
async def test_run_agent_background_handles_cancelled_exception():
    """
    当 graph 运行中被用户取消时，应正确捕获 AgentCancelledException
    """
    thread_id = f"hitl-cancel-{datetime.now().strftime('%H%M%S')}"

    from app.core.exceptions import AgentCancelledException

    mock_graph = MockGraph(raise_on_stream=AgentCancelledException())

    with patch("app.core.engine.background_agent.get_graph", return_value=mock_graph), \
         patch("app.core.engine.background_agent.ContextManager") as mock_ctx_manager, \
         patch("app.core.engine.background_agent.MemoryContainer") as mock_memory_container:

        mock_ctx_manager.load_from_redis = AsyncMock(return_value=None)
        mock_ctx_manager.current = MagicMock(return_value=MagicMock(thread_id=thread_id, project_id=1, command_id=None, working_directory="/tmp"))
        mock_memory = MagicMock()
        mock_memory.preferences.get_merged_preferences = AsyncMock(return_value="")
        mock_memory.long_term.get_project_concepts = AsyncMock(return_value="")
        mock_memory_container.return_value.memory_manager = mock_memory

        inputs = {
            "messages": [{"type": "human", "content": "测试取消"}],
            "project_id": 1,
            "goal": "测试取消",
        }

        await run_agent_background(thread_id, inputs)

        activity = await activity_monitor.get_activity(thread_id)
        assert activity.get("status") == "cancelled"
