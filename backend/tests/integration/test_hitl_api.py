"""
HITL (Human-in-the-Loop) API 层集成测试

测试范围:
- POST /api/v1/chat/resume
- POST /api/v1/hitl/cancel
- 验证端点参数校验、状态码、DB 持久化行为

运行方式:
    cd backend && python -m pytest tests/integration/test_hitl_api.py -v
"""

import os
import sys
import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

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

from fastapi import BackgroundTasks
from app.api.routes.agent import resume_chat, cancel_hitl_request, ChatRequest
from app.infrastructure.database.sql.database import Base, engine, session_scope
from app.models import Conversation, Message
from app.core.monitoring.activity import activity_monitor
from sqlmodel import SQLModel


@pytest.fixture(scope="module", autouse=True)
async def init_db():
    """模块级数据库初始化"""
    from app.core.config import settings

    if settings.EMBEDDED_MODE:
        from app import models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    yield


@pytest.fixture(autouse=True)
async def clean_state():
    """每个测试前清理表"""
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM messages"))
        await conn.execute(text("DELETE FROM conversations"))
        await conn.execute(text("DELETE FROM human_requests"))
    yield


class MockGraph:
    """模拟 LangGraph"""

    def __init__(self, state=None):
        self._state = state
        self.astream_calls = []

    async def astream(self, inputs, config=None):
        self.astream_calls.append({"inputs": inputs, "config": config})
        yield {"type": "mock_resume_event"}

    async def aget_state(self, config=None):
        return self._state


class MockState:
    def __init__(self, values=None):
        self.values = values or {}


async def seed_conversation(thread_id: str, project_id: int = 1):
    """在数据库中创建一个对话和一条用户消息"""
    async with session_scope() as session:
        conv = Conversation(
            id=thread_id,
            project_id=project_id,
            title="HITL Test Conversation",
        )
        session.add(conv)
        await session.flush()

        msg = Message(
            thread_id=thread_id,
            project_id=project_id,
            role="human",
            content="测试消息",
            sequence_number=1,
        )
        session.add(msg)
        return conv.id


@pytest.mark.asyncio
async def test_resume_chat_with_smart_tool_completion():
    """
    /chat/resume 在检测到 pending tool_call (ask_confirm) 时，
    应将 user_input 包装为 ToolMessage 而不是 HumanMessage
    """
    thread_id = f"api-resume-{datetime.now().strftime('%H%M%S')}"
    await seed_conversation(thread_id)

    mock_ai_msg = AIMessage(
        content="需要确认",
        tool_calls=[{
            "id": "call_api_123",
            "name": "ask_confirm",
            "args": {"action_description": "删除文件"}
        }]
    )
    mock_state = MockState(values={"messages": [mock_ai_msg]})
    mock_graph = MockGraph(state=mock_state)

    with patch("app.api.routes.agent.get_graph", return_value=mock_graph), \
         patch("app.api.routes.agent.get_checkpointer", return_value=MagicMock()), \
         patch("app.api.routes.agent.evocloud_manager") as mock_evocloud:

        mock_evocloud.upload_log = AsyncMock()
        bg_tasks = BackgroundTasks()

        result = await resume_chat(
            req=ChatRequest(thread_id=thread_id, message="APPROVED"),
            bg_tasks=bg_tasks,
        )

        assert result["status"] == "resuming"
        assert result["thread_id"] == thread_id

        # 等待后台任务执行
        await asyncio.sleep(0.5)

        # 验证 astream 收到的是 ToolMessage
        assert len(mock_graph.astream_calls) == 1
        inputs = mock_graph.astream_calls[0]["inputs"]
        assert inputs is not None
        assert "messages" in inputs
        assert len(inputs["messages"]) == 1
        assert isinstance(inputs["messages"][0], ToolMessage)
        assert inputs["messages"][0].tool_call_id == "call_api_123"
        assert inputs["messages"][0].content == "APPROVED"


@pytest.mark.asyncio
async def test_resume_chat_without_tool_call_uses_human_message():
    """
    当没有 pending tool_call 时，/chat/resume 应使用 HumanMessage
    """
    thread_id = f"api-human-{datetime.now().strftime('%H%M%S')}"
    await seed_conversation(thread_id)

    mock_state = MockState(values={"messages": []})
    mock_graph = MockGraph(state=mock_state)

    with patch("app.api.routes.agent.get_graph", return_value=mock_graph), \
         patch("app.api.routes.agent.get_checkpointer", return_value=MagicMock()), \
         patch("app.api.routes.agent.evocloud_manager") as mock_evocloud:

        mock_evocloud.upload_log = AsyncMock()
        bg_tasks = BackgroundTasks()

        await resume_chat(
            req=ChatRequest(thread_id=thread_id, message="继续吧"),
            bg_tasks=bg_tasks,
        )

        await asyncio.sleep(0.5)

        inputs = mock_graph.astream_calls[0]["inputs"]
        assert len(inputs["messages"]) == 1
        assert isinstance(inputs["messages"][0], HumanMessage)
        assert inputs["messages"][0].content == "继续吧"


@pytest.mark.asyncio
async def test_resume_chat_persists_user_message_to_db():
    """
    /chat/resume 应将用户回复持久化到 messages 表
    """
    thread_id = f"api-persist-{datetime.now().strftime('%H%M%S')}"
    await seed_conversation(thread_id)

    mock_state = MockState(values={"messages": []})
    mock_graph = MockGraph(state=mock_state)

    with patch("app.api.routes.agent.get_graph", return_value=mock_graph), \
         patch("app.api.routes.agent.get_checkpointer", return_value=MagicMock()), \
         patch("app.api.routes.agent.evocloud_manager") as mock_evocloud:

        mock_evocloud.upload_log = AsyncMock()
        bg_tasks = BackgroundTasks()

        await resume_chat(
            req=ChatRequest(thread_id=thread_id, message="我确认继续"),
            bg_tasks=bg_tasks,
        )

        await asyncio.sleep(0.5)

        # 验证数据库
        async with session_scope() as session:
            from sqlalchemy import select
            stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
            result = await session.execute(stmt)
            messages = result.scalars().all()

            assert len(messages) == 2  # 原始 + resume
            assert messages[1].role == "human"
            assert messages[1].content == "我确认继续"


@pytest.mark.asyncio
async def test_cancel_hitl_request_with_db_record():
    """
    /hitl/cancel 应取消 pending 的 DB 请求并恢复 graph
    """
    thread_id = f"api-cancel-{datetime.now().strftime('%H%M%S')}"
    await seed_conversation(thread_id)

    # 先创建一个 pending HITL 请求
    from app.domain.tools.human_input import create_request
    req = await create_request(
        thread_id=thread_id,
        request_type="approval",
        prompt="确认删除？",
        default_value="REJECTED",
    )

    mock_ai_msg = AIMessage(
        content="需要确认",
        tool_calls=[{
            "id": "call_cancel_1",
            "name": "ask_confirm",
            "args": {}
        }]
    )
    mock_state = MockState(values={"messages": [mock_ai_msg]})
    mock_graph = MockGraph(state=mock_state)

    with patch("app.api.routes.agent.get_graph", return_value=mock_graph), \
         patch("app.api.routes.agent.get_checkpointer", return_value=MagicMock()):

        bg_tasks = BackgroundTasks()
        result = await cancel_hitl_request(
            req=MagicMock(thread_id=thread_id, reason="用户不想继续"),
            bg_tasks=bg_tasks,
        )

        assert result["status"] == "cancelled"
        assert result["thread_id"] == thread_id
        assert result["request_id"] == req.id

        # 等待后台任务
        await asyncio.sleep(0.5)

        # 验证 astream 收到 ToolMessage(content="REJECTED")
        inputs = mock_graph.astream_calls[0]["inputs"]
        assert isinstance(inputs["messages"][0], ToolMessage)
        assert inputs["messages"][0].content == "REJECTED"


@pytest.mark.asyncio
async def test_cancel_hitl_request_without_db_record():
    """
    当只有 activity monitor 中的 transient 请求、没有 DB 记录时，
    /hitl/cancel 应返回成功且不尝试恢复 graph
    """
    thread_id = f"api-cancel-transient-{datetime.now().strftime('%H%M%S')}"
    await seed_conversation(thread_id)

    # 在 activity_monitor 中设置一个 human_request（但没有 DB 记录）
    await activity_monitor.set_human_request(
        thread_id=thread_id,
        request_data={"id": "transient-1", "type": "confirm", "prompt": "确认？"},
    )

    mock_graph = MockGraph()

    with patch("app.api.routes.agent.get_graph", return_value=mock_graph), \
         patch("app.api.routes.agent.get_checkpointer", return_value=MagicMock()):

        bg_tasks = BackgroundTasks()
        result = await cancel_hitl_request(
            req=MagicMock(thread_id=thread_id, reason=None),
            bg_tasks=bg_tasks,
        )

        assert result["status"] == "cancelled"
        assert result["request_id"] is None

        # 不应调用 graph.astream（因为没有 pending DB 请求）
        await asyncio.sleep(0.5)
        assert len(mock_graph.astream_calls) == 0


@pytest.mark.asyncio
async def test_resume_chat_with_temp_project_payload():
    """
    /chat/resume 支持 temp_project JSON payload（项目切换场景）
    """
    thread_id = f"api-temp-proj-{datetime.now().strftime('%H%M%S')}"
    await seed_conversation(thread_id)

    mock_state = MockState(values={"messages": []})
    mock_graph = MockGraph(state=mock_state)

    with patch("app.api.routes.agent.get_graph", return_value=mock_graph), \
         patch("app.api.routes.agent.get_checkpointer", return_value=MagicMock()), \
         patch("app.api.routes.agent.thread_context_store") as mock_store, \
         patch("app.api.routes.agent.evocloud_manager") as mock_evocloud:

        mock_evocloud.upload_log = AsyncMock()
        bg_tasks = BackgroundTasks()

        temp_project_payload = '{"type":"temp_project","project_id":99,"project_name":"TestProj"}'
        await resume_chat(
            req=ChatRequest(thread_id=thread_id, message=temp_project_payload),
            bg_tasks=bg_tasks,
        )

        await asyncio.sleep(0.5)

        # 验证 temp_project 被存储
        mock_store.set_temp_project.assert_called_once_with(thread_id, 99)

        # 验证输入是系统信号消息
        inputs = mock_graph.astream_calls[0]["inputs"]
        assert isinstance(inputs["messages"][0], HumanMessage)
        assert "Selected project: TestProj" in inputs["messages"][0].content
