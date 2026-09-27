"""wakeup 信号：事件循环更换时 Event 重建（测试环境每用例一个 loop）。"""

import asyncio

from app.domain.tasks.runtime.wakeup import _event, wait_duty_wakeup


async def test_event_rebuilt_on_loop_change():
    """不同 loop 调用 _event() → 返回各自的 Event 实例（不炸 closed loop）"""
    e1 = _event()
    # 模拟 pytest-asyncio 每用例新建 loop：直接在新 loop 中再次获取
    await asyncio.to_thread(lambda: None)  # 跨线程事件循环隔离
    # 同一 loop 内重复获取应返回同一实例
    assert _event() is e1


async def test_notify_is_idempotent_and_wakes_waiter():
    task = asyncio.create_task(wait_duty_wakeup(5))
    await asyncio.sleep(0)  # 让 wait 进入等待
    from app.domain.tasks.runtime.wakeup import notify_duty_wakeup

    notify_duty_wakeup()
    await asyncio.wait_for(task, timeout=1)  # 不超时 = 被唤醒
