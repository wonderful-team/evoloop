"""
API 入口全链路集成测试 — 验证能力寻址参数 skill_ids 到引擎调度的贯通
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid
import time
from app.api.schemas.agent import ChatRequest
from app.models.learning import LearnedSkill
from app.core.context import ContextManager

@pytest.mark.asyncio
async def test_api_chat_endpoint_skill_ids_flow():
    """
    测试当 API 接收到带有 skill_ids: [41, 8] 的请求时，
    能否正确在 DB 查询实体、组装为 reference 并分发给底层 dispatch_agent_run
    """
    from app.api.routes.agent import chat_endpoint

    # 1. 准备测试 Payload
    req = ChatRequest(
        thread_id=str(uuid.uuid4()),
        project_id=1,
        message="请分析本地销售数据",
        skill_ids=[41, 8],
        model="gpt-4o"
    )

    # 2. 模拟数据库返回的 LearnedSkill 专家技能实体
    mock_skill_1 = LearnedSkill(id=41, name="universal_data_analytics", description="通用数据分析 SOP")
    mock_skill_2 = LearnedSkill(id=8, name="python_code_specialist", description="Python 脚本高级重构 SOP")

    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = [mock_skill_1, mock_skill_2]

    # 3. 模拟 dispatch_agent_run 与后台任务添加
    mock_dispatch_res = MagicMock()
    mock_dispatch_res.status = "success"
    mock_dispatch_res.message_id = "msg-12345"
    mock_dispatch_res.inputs = {"messages": []}

    mock_bg_tasks = MagicMock()

    # 4. 执行调用与断言验证
    with patch("app.api.routes.agent.session_scope") as mock_scope:
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_db_result
        mock_scope.return_value.__aenter__.return_value = mock_session

        with patch("app.api.routes.agent.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = mock_dispatch_res

            res = await chat_endpoint(req, mock_bg_tasks, MagicMock())

            # 断言接口响应正确
            assert res["status"] == "queued"
            assert res["thread_id"] == req.thread_id
            assert res["message_id"] == "msg-12345"

            # 核心断言：验证传递给 dispatch_agent_run 的 references 是否正确包含了传入的多专家技能
            mock_dispatch.assert_called_once()
            _, kwargs = mock_dispatch.call_args
            
            passed_references = kwargs["references"]
            assert len(passed_references) == 2
            
            ref1, ref2 = passed_references[0], passed_references[1]
            assert ref1["type"] == "skill"
            assert ref1["target_id"] == "41"
            assert ref1["metadata"]["skill_name"] == "universal_data_analytics"
            
            assert ref2["type"] == "skill"
            assert ref2["target_id"] == "8"
            assert ref2["metadata"]["skill_name"] == "python_code_specialist"
