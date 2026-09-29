"""message 引用 metadata 直通契约测试。

值守评审（review.py）经 dispatch_agent_run(references=...) 注入的 message 引用
携带 metadata.thread_id / task_id——前端「执行会话」胶囊点击定位执行线程依赖它。
process_references 若丢弃调用方 metadata（曾只写 {"snippet"}），胶囊退化为死链。
"""

from app.core.engine.message.reference import ReferenceService


class _SessionMissingMessage:
    """最小 session 桩：消息不存在（snippet=None 分支）。"""

    async def get(self, *args, **kwargs):
        return None


async def test_message_reference_metadata_preserved():
    service = ReferenceService()
    ref_in = {
        "type": "message",
        "target_id": "msg-1",
        "target_name": "执行会话 (#T-1)",
        "metadata": {"thread_id": "wakeup_1_task", "task_id": "t-1"},
    }
    context = await service.process_references(
        message_text="",
        references_input=[ref_in],
        session=_SessionMissingMessage(),
    )
    assert len(context.references) == 1
    persisted = context.references[0]
    assert persisted["type"] == "message"
    assert persisted["target_id"] == "msg-1"
    assert persisted["metadata"]["thread_id"] == "wakeup_1_task"
    assert persisted["metadata"]["task_id"] == "t-1"
    assert "snippet" in persisted["metadata"]


async def test_message_reference_meta_data_alias_preserved():
    """meta_data 命名同样直通（与 MessageReference 表列名对齐的调用方）。"""
    service = ReferenceService()
    ref_in = {
        "type": "message",
        "target_id": "msg-2",
        "target_name": "执行会话",
        "meta_data": {"thread_id": "th-2"},
    }
    context = await service.process_references(
        message_text="",
        references_input=[ref_in],
        session=_SessionMissingMessage(),
    )
    assert context.references[0]["metadata"]["thread_id"] == "th-2"
