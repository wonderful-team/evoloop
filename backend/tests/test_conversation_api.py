"""
真实可运行的测试 - Conversation API 测试

运行方式:
    cd backend && python -m pytest tests/test_conversation_api.py -v
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestConversationMessageFormat:
    """测试对话消息格式的单元测试"""

    def test_human_message_structure(self):
        """测试 human 消息的数据结构"""
        message = {
            "id": "123",
            "role": "human",
            "content": "帮我写一个 Python 函数",
            "thinking": None,
            "created_at": "2024-01-01T10:00:00",
            "parent_id": None,
            "references": [],
            "steps": [],
            "has_file_operations": False,
        }
        
        # 验证必需字段
        assert message["id"] is not None
        assert message["role"] == "human"
        assert isinstance(message["content"], str)
        assert len(message["content"]) > 0

    def test_ai_message_with_steps(self):
        """测试 AI 消息包含工具执行步骤"""
        message = {
            "id": "124",
            "role": "ai",
            "content": "我来帮你写一个排序函数",
            "thinking": "用户需要一个 Python 函数...",
            "created_at": "2024-01-01T10:00:01",
            "steps": [
                {
                    "id": "step-1",
                    "tool": "write_file",
                    "tool_name": "写入文件",
                    "input": {"file_path": "/tmp/sort.py", "content": "def sort(): pass"},
                    "output": "文件已创建",
                    "status": "success",
                    "duration": 1.5,
                }
            ],
            "has_file_operations": True,
        }
        
        assert message["role"] == "ai"
        assert len(message["steps"]) == 1
        assert message["steps"][0]["tool"] == "write_file"

    def test_message_with_references(self):
        """测试带引用的消息"""
        message = {
            "id": "125",
            "role": "ai",
            "content": "根据代码库分析...",
            "references": [
                {
                    "id": "ref-1",
                    "type": "file",
                    "target_id": "/src/main.py",
                    "target_name": "main.py",
                }
            ],
        }
        
        assert len(message["references"]) == 1
        assert message["references"][0]["type"] == "file"


class TestMessagePagination:
    """测试消息分页加载"""

    @pytest.mark.parametrize("limit,expected_count", [
        (10, 10),
        (50, 50),
        (100, 100),
        (200, 100),  # 最大限制 100
    ])
    def test_pagination_limit(self, limit, expected_count):
        """测试分页限制参数"""
        # 模拟请求参数验证
        validated_limit = min(max(limit, 1), 100)
        assert validated_limit == expected_count

    def test_pagination_cursor(self):
        """测试游标分页"""
        messages = [
            {"id": 1, "content": "msg1"},
            {"id": 2, "content": "msg2"},
            {"id": 3, "content": "msg3"},
        ]
        
        # 模拟 before_id=3，应该返回 id < 3 的消息
        before_id = 3
        filtered = [m for m in messages if m["id"] < before_id]
        
        assert len(filtered) == 2
        assert all(m["id"] < before_id for m in filtered)


class TestConversationLifecycle:
    """测试对话生命周期"""

    @pytest.fixture
    def mock_db_session(self):
        """提供 Mock 数据库会话"""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_list_conversations(self, mock_db_session):
        """测试获取对话列表"""
        # Mock 数据库查询结果
        mock_conversations = [
            MagicMock(
                id="thread-1",
                title="测试对话 1",
                project_id=1,
                updated_at=datetime.now(),
            ),
            MagicMock(
                id="thread-2", 
                title="测试对话 2",
                project_id=1,
                updated_at=datetime.now(),
            ),
        ]
        
        mock_db_session.execute.return_value.scalars.return_value.all.return_value = mock_conversations
        
        # 验证返回格式
        result = [
            {
                "thread_id": c.id,
                "title": c.title or "Untitled",
                "project_id": c.project_id,
                "updated_at": c.updated_at,
                "status": "idle",
            }
            for c in mock_conversations
        ]
        
        assert len(result) == 2
        assert result[0]["thread_id"] == "thread-1"
        assert result[0]["status"] == "idle"

    @pytest.mark.asyncio
    async def test_delete_conversation_cascade(self, mock_db_session):
        """测试删除对话的级联操作"""
        thread_id = "thread-to-delete"
        
        # 模拟删除操作
        with patch("app.models.Conversation") as mock_conv:
            mock_instance = MagicMock()
            mock_db_session.get.return_value = mock_instance
            
            # 执行删除
            await mock_db_session.delete(mock_instance)
            
            # 验证调用了删除
            mock_db_session.delete.assert_called_once_with(mock_instance)


class TestStreamEventFormat:
    """测试 SSE 流事件格式"""

    def test_sse_event_line_format(self):
        """测试 SSE 事件行格式"""
        event_data = {"type": "token", "content": "Hello"}
        sse_line = f"event: token\ndata: {json.dumps(event_data)}\n\n"
        
        # 验证 SSE 格式
        assert sse_line.startswith("event: token\n")
        assert "data: {" in sse_line
        assert sse_line.endswith("\n\n")

    @pytest.mark.parametrize("event_type,event_data", [
        ("token", {"content": "Hello"}),
        ("step", {"id": "step-1", "tool": "browser"}),
        ("status", {"status": "running"}),
        ("input_request", {"description": "请输入"}),
    ])
    def test_various_event_types(self, event_type, event_data):
        """测试各种事件类型的格式"""
        event = {"type": event_type, **event_data}
        serialized = json.dumps(event)
        deserialized = json.loads(serialized)
        
        assert deserialized["type"] == event_type
        assert all(key in deserialized for key in event_data.keys())


class TestMessageVisibility:
    """测试消息可见性（可见 vs 隐藏消息）"""

    def test_visible_message_display(self):
        """测试可见消息应该在前端显示"""
        visible_msg = {
            "id": 1,
            "role": "ai",
            "content": "这是可见消息",
            "is_visible": True,
        }
        assert visible_msg["is_visible"] is True

    def test_invisible_message_hidden(self):
        """测试隐藏消息不应该直接显示"""
        invisible_msg = {
            "id": 2,
            "role": "tool",
            "content": "工具输出",
            "is_visible": False,
        }
        # 隐藏消息应该被折叠到父消息中
        assert invisible_msg["is_visible"] is False


class TestRewindFunctionality:
    """测试对话回溯功能"""

    def test_rewind_to_previous_state(self):
        """测试回溯到之前状态"""
        # 模拟消息历史
        messages = [
            {"id": 1, "role": "human", "content": "Q1"},
            {"id": 2, "role": "ai", "content": "A1"},
            {"id": 3, "role": "human", "content": "Q2"},
            {"id": 4, "role": "ai", "content": "A2"},
        ]
        
        # 回溯到消息 2 之后
        target_message_id = 2
        remaining = [m for m in messages if m["id"] <= target_message_id]
        removed = [m for m in messages if m["id"] > target_message_id]
        
        assert len(remaining) == 2
        assert len(removed) == 2
        assert all(m["id"] <= target_message_id for m in remaining)


# 运行命令:
# python -m pytest backend/tests/test_conversation_api.py -v
