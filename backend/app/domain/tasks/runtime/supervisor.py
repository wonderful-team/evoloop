"""Duty supervisor — 自主值守的连续运行主循环（domain 层）。

业务层的运行时自治：reconcile → dispatch → wait(wakeup, 60s) 的编排属于
自主值守域本身；main.py lifespan 作为组合根负责拉起，本域不依赖任何
infrastructure 之上的层。

设计不变式（AGENTS.md「自主值守（任务队列）关键事实」）：
- 事件只做加速，60s 超时兜底 —— 任何丢失的信号最多损失实时性，不损失存活性；
- 单 drainer：任务队列派发只发生在本循环（tick 已摘除），跨进程双派发窗口关闭；
- HITL 挂起是合法状态（等人决策）：runner 吞中断正常 return，drain 继续认领
  下一个任务，值守循环不停摆；
- 稳态下周期性 reconcile 兜底死亡现场（详见 reconciler.py）。
"""

from __future__ import annotations

import logging
import time

from app.domain.tasks.constants import (
    DRAIN_IDLE_TIMEOUT_SECONDS,
    RECONCILE_INTERVAL_SECONDS,
)
from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks
from app.domain.tasks.runtime.reconciler import reconcile_stranded
from app.domain.tasks.runtime.wakeup import wait_duty_wakeup

logger = logging.getLogger(__name__)


async def run_supervisor_forever() -> None:
    """值守主循环：reconcile → drain → wait(wakeup, 60s)。永不正常返回。

    - 启动即先 reconcile（startup 语义：上一进程遗留的 running 全部判死）再 drain，
      离线补跑语义由 tick 的启动补扫 + 此处共同覆盖；
    - 稳态下每 RECONCILE_INTERVAL_SECONDS 强制 reconcile 一次（独立于唤醒信号）。
    """
    logger.info(
        "[DutySupervisor] 已启动（事件驱动 + %.0fs 兜底）",
        DRAIN_IDLE_TIMEOUT_SECONDS,
    )
    try:
        await reconcile_stranded(startup=True)
    except Exception:
        # 启动收敛失败不得杀死值守主循环：稳态周期 reconcile 会重试收敛
        logger.exception("[DutySupervisor] startup reconcile 失败（循环继续，稳态兜底）")
    last_reconcile = time.monotonic()
    while True:
        try:
            await dispatch_due_tasks()
        except Exception:
            logger.exception("[DutySupervisor] drain failed")
        await wait_duty_wakeup(DRAIN_IDLE_TIMEOUT_SECONDS)
        if time.monotonic() - last_reconcile >= RECONCILE_INTERVAL_SECONDS:
            try:
                await reconcile_stranded()
            except Exception:
                logger.exception("[DutySupervisor] reconcile failed")
            last_reconcile = time.monotonic()
