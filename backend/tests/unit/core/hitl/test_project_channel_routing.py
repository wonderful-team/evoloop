"""HITL 事件的项目频道路由回归（2026-09-23 收敛：hitl_created/resolved
从只发全局频道改为同发项目频道——项目级订阅此前收不到审批事件）。"""

import pytest

from app.core.hitl.core import _task_channel_for_thread


@pytest.mark.parametrize(
    ("thread_id", "expected"),
    [
        # 值守四前缀：pid 是第二段
        ("wakeup_183_task-uuid-1", "tasks:183:events"),
        ("duty_7_wxid_abc", "tasks:7:events"),
        ("kf_120_order-1001", "tasks:120:events"),
        ("agent_9_stage-3", "tasks:9:events"),
        # pid 含下划线分隔的富线程名：取第一段数字
        ("wakeup_183_a1b2c3-456", "tasks:183:events"),
    ],
)
def test_duty_thread_resolves_project_channel(thread_id: str, expected: str):
    assert _task_channel_for_thread(thread_id) == expected


@pytest.mark.parametrize(
    "thread_id",
    [
        "",  # 空
        "conv-uuid-999",  # 普通对话线程：无项目频道（只发全局）
        "wakeup_",  # 前缀但无 pid
        "wakeup_abc_notnumeric",  # pid 非数字
    ],
)
def test_non_duty_thread_returns_none(thread_id: str):
    assert _task_channel_for_thread(thread_id) is None
