"""值守调度接入 — run_duty_poll 轻量轮巡任务。

与 AutonomousTask 现有执行链（依赖 Android 设备池）解耦：
值守轮巡不需要设备，直接 dispatch_agent_run → run_agent_background。

调度仍可复用 AutonomousTask（定时触发），但执行走独立路径 run_duty_poll。

执行模型：串行队列 + 按种类判定。
- 所有轮巡任务串行执行（同一时刻只处理一个，不同种类排队等执行）；
- 任务带"种类"（企微线 wecom / 业务巡检 business_poll 等）；
- 同种类：上一个还没处理完时，新到同类任务直接跳过；
- 不同种类：互不跳过，按序排队执行。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.channel.duty.config import load_duty_config
from app.core.channel.duty.wecom.channel import WeComDutyChannel
from app.infrastructure.queue.factory import shared_task

logger = logging.getLogger(__name__)

# 值守任务标记（params_template 里携带，dispatch 时用于分流）
DUTY_PARAM_MARKER = "duty_channel"

# 值守任务种类
KIND_WECOM = "wecom"  # 企微线：客户消息轮巡
KIND_BUSINESS_POLL = "business_poll"  # 运营线：业务巡检

# 全局串行执行锁：不同种类任务排队执行，同一时刻只处理一个轮巡任务。
_exec_lock = asyncio.Lock()

# 正在进行中的任务种类集合（单 worker 事件循环内，无竞态）。
_active_kinds: set[str] = set()

T = TypeVar("T")


async def _run_kind(kind: str, run: Callable[[], Awaitable[T]]) -> T | None:
    """按种类执行一个轮巡任务。

    到达即占用 kind：同种类上一个还没处理完时，新到同类任务直接跳过；
    不同种类不互斥，排队等全局串行锁执行。
    """
    if kind in _active_kinds:
        logger.info("[duty] 同种类任务仍在进行（kind=%s），跳过", kind)
        return None
    _active_kinds.add(kind)
    try:
        async with _exec_lock:
            return await run()
    finally:
        _active_kinds.discard(kind)


async def _run_duty_poll_impl(project_id: int, kind: str | None = None) -> int:
    """值守轮巡核心实现（不依赖 Android 设备池）。

    Args:
        kind: 指定执行种类；None 则按顺序执行企微线 + 业务巡检（兼容旧调度）。
    """
    # 初始化 evocloud_manager，确保 worker 里 Agent LLM 调用有 Gateway token
    # （否则 get_token() 空，LLM 推理挂起）
    from app.core.evocloud.manager import evocloud_manager

    _ = evocloud_manager.api  # 触发 initialize
    await evocloud_manager.get_token()

    cfg = await load_duty_config(project_id)
    if not cfg or not cfg["enabled"]:
        logger.info("[wecom_duty] 项目 %s 未开启值守或无配置，跳过", project_id)
        return 0

    # 类单例：WeComDutyChannel 自持 __new__ 单例（仅订阅事件一次），
    # 项目数据（history_dir）每次按 project_id 从配置读取（§6.8.1）
    channel = WeComDutyChannel()
    cfg["project_id"] = project_id
    channel.bind_project(cfg)

    total = 0
    # 双线轮巡，按种类执行：
    # ① 企微线（kind=wecom）：客户未读 → Agent 回复
    # ② 业务巡检（kind=business_poll）：扫描 prompts 列表，到期的逐条发 Agent
    if kind in (None, KIND_WECOM):
        handled = await _run_kind(KIND_WECOM, lambda: channel.poll_once(project_id))
        total += handled or 0
    if kind in (None, KIND_BUSINESS_POLL):
        business = await _run_kind(
            KIND_BUSINESS_POLL, lambda: channel.business_poll_check(project_id)
        )
        total += business or 0
    return total


@shared_task(name="run_duty_poll")
async def run_duty_poll(project_id: int, kind: str | None = None) -> int:
    """执行一次值守轮巡，返回处理的消息数（0 = 无新消息快速路径）。

    Args:
        kind: 指定执行种类；None 则同时执行企微线 + 业务巡检。
    """
    handled = await _run_duty_poll_impl(project_id=project_id, kind=kind)
    return handled


def task_is_duty(task_params: dict | None) -> bool:
    """判断 AutonomousTask 是否为值守任务（params_template 带值守标记）。"""
    if not task_params:
        return False
    return bool(task_params.get(DUTY_PARAM_MARKER))
