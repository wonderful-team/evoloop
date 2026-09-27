"""Duty wakeup signal — 自主值守的域内唤醒信号。

事件只做加速，不做依赖：任何丢失的唤醒都由 supervisor 的固定超时兜底收敛
（AGENTS.md「自主值守（任务队列）关键事实」——电平触发模型，状态在队列里）。

- `notify_duty_wakeup()`：任意生产方调用（run 终态事件 / 队列变更），幂等；
- `wait_duty_wakeup(timeout)`：supervisor 等待，超时静默返回（= 兜底轮询语义），
  返回前清除信号，等待期间到达的唤醒不会被吞；
- 订阅者归口 `../event/subscribers.py`（DutyWakeupSubscriber）。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_wakeup: asyncio.Event | None = None
_wakeup_loop: asyncio.AbstractEventLoop | None = None


def _event() -> asyncio.Event:
    global _wakeup, _wakeup_loop
    loop = asyncio.get_running_loop()
    if _wakeup is None or _wakeup_loop is not loop:
        # 事件循环更换时重建（生产单循环只建一次；测试每用例一个 loop）。
        # 电平触发模型 + supervisor 60s 兜底：旧 loop 上残留的信号丢失最多
        # 损失实时性，不损失存活性（AGENTS.md 设计不变式）。
        _wakeup = asyncio.Event()
        _wakeup_loop = loop
    return _wakeup


def notify_duty_wakeup() -> None:
    """登记一次唤醒（幂等；多个来源并发触发合并为一次）。"""
    _event().set()


async def wait_duty_wakeup(timeout: float) -> None:
    """等待唤醒信号；超时返回（兜底语义），返回时清信号。

    竞态说明：wait 返回后、clear 前到达的 notify 会保留在信号里，下一轮
    wait 立即返回——最坏情况是多跑一轮空 drain，不丢唤醒。
    """
    event = _event()
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        event.clear()
