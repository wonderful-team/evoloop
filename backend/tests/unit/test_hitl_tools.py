"""
HITL (Human-in-the-Loop) 工具层单元测试

测试范围:
- ask_human / ask_confirm 工具的行为
- HumanRequest 数据库记录的生命周期
- 异常抛出 (AgentHumanInterruptException)

运行方式:
    cd backend && python -m pytest tests/unit/test_hitl_tools.py -v
"""

import os
import sys
import pytest
import uuid

# 确保能导入 backend 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# 加载 .env
env_path = os.path.join(os.path.dirname(__file__), "../../../.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

# Mock pgvector 模块（在非 PostgreSQL 环境下）
# 需要提供一个可用的 Vector 类，因为 codebase.py 中的 CodeChunk 模型依赖它
from unittest.mock import MagicMock
from sqlalchemy import TypeDecorator, Float

class MockVector(TypeDecorator):
    """Mock pgvector Vector type for testing"""
    impl = Float
    cache_ok = True
    
    def __init__(self, dimensions=None):
        super().__init__()
        self.dimensions = dimensions
    
    def get_col_spec(self, **kw):
        return f"VECTOR({self.dimensions})" if self.dimensions else "VECTOR"

mock_pgvector = MagicMock()
mock_pgvector.sqlalchemy.Vector = MockVector
sys.modules["pgvector"] = mock_pgvector
sys.modules["pgvector.sqlalchemy"] = mock_pgvector.sqlalchemy

from app.core.exceptions import AgentHumanInterruptException
from app.domain.tools.human_input import (
    ask_human,
    ask_confirm,
    create_request,
    complete_request,
    cancel_request,
    get_pending_request,
    get_pending_requests_for_thread,
)
from app.infrastructure.database.sql.database import Base, engine, session_scope
# 直接从 conversation 模块导入，避免导入完整的 models（包含 pgvector 依赖）
from app.models.conversation import HumanRequest
from sqlmodel import SQLModel


@pytest.fixture(scope="module", autouse=True)
async def init_db():
    """模块级数据库初始化（仅 SQLite Embedded 模式）"""
    from app.core.config import settings

    if settings.EMBEDDED_MODE:
        from app import models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    yield

    # 清理 HumanRequest 表
    try:
        from sqlalchemy import text

        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM human_requests"))
    except Exception:
        pass


@pytest.fixture(autouse=True)
async def clean_human_requests():
    """每个测试前清理 human_requests 表"""
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM human_requests"))
    yield


class TestAskHumanTool:
    """测试 ask_human 工具"""

    @pytest.mark.asyncio
    async def test_ask_human_raises_interrupt_and_creates_db_record(self):
        """调用 ask_human 应抛出 AgentHumanInterruptException 并在 DB 创建 pending 记录"""
        thread_id = f"test-thread-{uuid.uuid4().hex[:8]}"

        with pytest.raises(AgentHumanInterruptException) as exc_info:
            await ask_human(
                prompt="请输入你的名字",
                input_type="text",
                context="测试上下文",
                default_value="默认名字",
            )

        assert exc_info.value.request_id is not None
        request_id = exc_info.value.request_id

        # 验证数据库记录
        pending = await get_pending_requests_for_thread(thread_id)
        # 注意：ask_human 内部通过 ContextManager.current() 获取 thread_id
        # 如果当前没有上下文，thread_id 会是 "unknown"
        # 这里我们至少验证记录存在且状态正确
        all_pending = await get_pending_requests_for_thread("unknown")
        matched = [r for r in all_pending if r.id == request_id]
        assert len(matched) == 1
        assert matched[0].request_type == "text"
        assert matched[0].status == "pending"
        assert matched[0].prompt == "请输入你的名字"
        assert matched[0].default_value == "默认名字"

    @pytest.mark.asyncio
    async def test_ask_human_choice_requires_options(self):
        """choice 类型必须提供 options，否则直接返回错误而不创建请求"""
        result = await ask_human(
            prompt="请选择",
            input_type="choice",
            options=None,
        )
        assert "error" in result.lower() or "选项" in result

        # 验证没有创建 DB 记录
        all_pending = await get_pending_requests_for_thread("unknown")
        choice_records = [r for r in all_pending if r.prompt == "请选择"]
        assert len(choice_records) == 0

    @pytest.mark.asyncio
    async def test_ask_human_choice_with_options_creates_request(self):
        """choice 类型提供 options 时正常创建请求并中断"""
        with pytest.raises(AgentHumanInterruptException) as exc_info:
            await ask_human(
                prompt="请选择颜色",
                input_type="choice",
                options=["红", "绿", "蓝"],
            )

        request_id = exc_info.value.request_id
        all_pending = await get_pending_requests_for_thread("unknown")
        matched = [r for r in all_pending if r.id == request_id]
        assert len(matched) == 1
        assert matched[0].options == ["红", "绿", "蓝"]


class TestAskConfirmTool:
    """测试 ask_confirm 工具"""

    @pytest.mark.asyncio
    async def test_ask_confirm_raises_interrupt_with_approval_request(self):
        """调用 ask_confirm 应创建 approval 请求并中断"""
        with pytest.raises(AgentHumanInterruptException) as exc_info:
            await ask_confirm(
                action_description="删除文件 /tmp/test.txt",
                risk_level="high",
                details="此操作不可撤销",
                consequences="文件将永久丢失",
            )

        request_id = exc_info.value.request_id
        all_pending = await get_pending_requests_for_thread("unknown")
        matched = [r for r in all_pending if r.id == request_id]
        assert len(matched) == 1
        assert matched[0].request_type == "approval"
        assert matched[0].default_value == "REJECTED"
        assert "删除文件 /tmp/test.txt" in matched[0].prompt
        assert "high" in matched[0].context.lower() or "高风险" in matched[0].context


class TestRequestLifecycle:
    """测试 HITL 请求的生命周期管理"""

    @pytest.mark.asyncio
    async def test_create_and_complete_request(self):
        """创建请求并完成它"""
        req = await create_request(
            thread_id="lifecycle-test",
            request_type="text",
            prompt="测试请求",
            context="测试上下文",
            default_value="默认值",
        )

        assert req.id is not None
        assert req.status == "pending"

        # 完成请求
        success = await complete_request(req.id, "用户回复内容")
        assert success is True

        # 验证状态更新
        updated = await get_pending_request(req.id)
        assert updated is not None
        assert updated.status == "completed"
        assert updated.response == "用户回复内容"

    @pytest.mark.asyncio
    async def test_create_and_cancel_request(self):
        """创建请求并取消它"""
        req = await create_request(
            thread_id="lifecycle-test",
            request_type="confirmation",
            prompt="确认取消？",
        )

        success = await cancel_request(req.id)
        assert success is True

        updated = await get_pending_request(req.id)
        assert updated is not None
        assert updated.status == "cancelled"

    @pytest.mark.asyncio
    async def test_complete_nonexistent_request_returns_false(self):
        """完成不存在的请求应返回 False"""
        success = await complete_request("non-existent-id", "回复")
        assert success is False

    @pytest.mark.asyncio
    async def test_get_pending_requests_for_thread_filters_by_status(self):
        """get_pending_requests_for_thread 只返回 pending 状态的请求"""
        thread_id = f"filter-test-{uuid.uuid4().hex[:8]}"

        # 创建 2 个 pending 请求
        req1 = await create_request(thread_id=thread_id, request_type="text", prompt="p1")
        req2 = await create_request(thread_id=thread_id, request_type="text", prompt="p2")

        # 完成其中一个
        await complete_request(req1.id, "done")

        # 查询 pending
        pending = await get_pending_requests_for_thread(thread_id)
        assert len(pending) == 1
        assert pending[0].id == req2.id
