"""SchedulerLifecycleSubscriber — 触发器层心跳生命周期（模块自治）。

AutonomousTask 已收缩为纯定时器：本订阅者管理的循环只点火值守机械轮巡
（wecom GUI / mcp_message poll 兜底），不在本循环派发任何工作项
（ProjectTask 队列由 domain/tasks 的 supervisor 单 drainer 排空）。

进程归属：API 进程（main.py lifespan 发布 APP_STARTED）；worker 进程
（bin/run_worker.py）不发布 APP_STARTED，心跳不会在 worker 启动。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType

logger = logging.getLogger(__name__)

# tick 心跳间隔（秒）：对齐原 main.py 循环粒度
TICK_INTERVAL_SECONDS = 60


@event_register()
class SchedulerLifecycleSubscriber:
    """触发器层心跳：APP_STARTED 拉起 tick 循环 / APP_STOPPING 停止。"""

    def __init__(self) -> None:
        self.tick_task: asyncio.Task | None = None

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_app_started(self, event: Any) -> None:
        if self.tick_task is not None and not self.tick_task.done():
            logger.warning("[Scheduler] 心跳已在运行，忽略重复启动")
            return
        self.tick_task = asyncio.create_task(self._loop(), name="duty-scheduler-tick")
        logger.info("[Scheduler] 触发器层心跳已随 APP_STARTED 启动 (API 进程)")

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_app_stopping(self, event: Any) -> None:
        if self.tick_task is None:
            return
        self.tick_task.cancel()
        try:
            await self.tick_task
        except asyncio.CancelledError:
            pass
        logger.info("[Scheduler] 触发器层心跳已随 APP_STOPPING 停止")
        self.tick_task = None

    async def _loop(self) -> None:
        from app.infrastructure.scheduler.service import SchedulerService

        # 先 tick 后 sleep：启动即补扫 —— tick 按 next_run_at <= now 扫描，
        # 进程离线期间到期的触发器在重启后首轮全部命中（离线补跑语义，
        # 依赖此顺序，勿改为先 sleep）。
        while True:
            try:
                await SchedulerService.tick()
            except Exception:
                logger.exception("[Scheduler] tick 执行失败")
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
