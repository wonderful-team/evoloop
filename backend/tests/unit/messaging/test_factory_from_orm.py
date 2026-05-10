"""
检测 MessageBlockFactory.from_orm 对各类消息的转换是否完好。

核心目标：确保 tool 消息不会因为 display_name 渲染报错而被静默丢弃。
"""
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

import pytest
import logging
from datetime import datetime
from app.core.engine.message.factory import MessageBlockFactory
from app.core.engine.message.folder import MessageNormalizer


class FakeMessage:
    """模拟数据库 Message ORM 对象"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_from_orm_tool_message():
    """
    这个测试会在 bug 存在时直接失败：
    ToolRegistryMetadata.get_display_name() got an unexpected keyword argument 'status'
    """
    msg = FakeMessage(
        id="msg-test-001",
        thread_id="thread-123",
        role="tool",
        content="file content here",
        tool_name="read_file",
        tool_call_id="call_abc",
        meta_data={
            "input": {"path": "src/main.py"},
            "output": "content...",
            "tool_meta": {"display_name": "读取文件"},
        },
        status="completed",
        sequence_number=1,
        created_at=datetime.now(),
    )

    block = MessageBlockFactory.from_orm(msg)

    assert block is not None
    assert block.role == "tool"
    assert block.tool_name == "read_file"
    assert block.content == "file content here"
    assert block.tool_meta is not None


def test_normalize_preserves_tool_messages(caplog):
    """
    检测 normalize() 不会因为 from_orm 抛异常而静默丢弃 tool 消息。

    关键：即使 from_orm 内部报错，也不应该让整条消息从列表中消失。
    用 caplog 监控是否有错误日志被吞掉。
    """
    caplog.set_level(logging.ERROR, logger="app.core.engine.message.folder")

    tool_msg = FakeMessage(
        id="msg-test-002",
        thread_id="thread-123",
        role="tool",
        content="dir listing",
        tool_name="list_directory",
        tool_call_id="call_def",
        meta_data={"input": {"path": "src"}},
        status="completed",
        sequence_number=2,
        created_at=datetime.now(),
    )
    ai_msg = FakeMessage(
        id="msg-test-003",
        thread_id="thread-123",
        role="ai",
        content="I will read the file",
        meta_data={},
        status="completed",
        sequence_number=3,
        created_at=datetime.now(),
    )

    messages = [tool_msg, ai_msg]
    normalized = MessageNormalizer.normalize(messages)

    ids = [m.id for m in normalized]

    # 关键断言：tool 消息不应该被吞掉
    assert "msg-test-002" in ids, (
        f"tool message was silently dropped. "
        f"Remaining IDs: {ids}. "
        f"Captured errors: {[r.message for r in caplog.records]}"
    )
    assert "msg-test-003" in ids, "ai message was unexpectedly dropped"

    # 更严格：normalize 过程不应该产生 ERROR 级别的日志
    # （如果有 ERROR 日志，说明 from_orm 在抛异常被吞了）
    error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(error_logs) == 0, (
        f"normalize() swallowed errors: {[r.message for r in error_logs]}. "
        f"This means some messages were silently lost."
    )


def test_normalize_does_not_drop_any_message():
    """
    输入 N 条消息，输出也必须是 N 条（除非显式过滤）。
    """
    messages = [
        FakeMessage(
            id=f"msg-{i}",
            thread_id="thread-123",
            role="tool" if i % 2 == 0 else "ai",
            content=f"content-{i}",
            tool_name="read_file" if i % 2 == 0 else None,
            tool_call_id=f"call-{i}" if i % 2 == 0 else None,
            meta_data={"input": {"path": "src"}} if i % 2 == 0 else {},
            status="completed",
            sequence_number=i,
            created_at=datetime.now(),
        )
        for i in range(10)
    ]

    normalized = MessageNormalizer.normalize(messages)

    assert len(normalized) == 10, (
        f"Expected 10 messages after normalize, got {len(normalized)}. "
        f"Some messages were silently dropped!"
    )
