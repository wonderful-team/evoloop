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
import time
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


# ── 在飞登记（防积压）──────────────────────────────────────
# 背景：SchedulerService.dispatch_task 只认 next_run_at<=now 就 .delay() 投递，
# 不感知该 (project_id, kind) 是否已在飞（排队中或执行中）。单轮执行时长 >
# interval 时，每 60s tick 都会再投一份，Huey 队列（持久化）持续积压重复副本。
# 修复：dispatch 投递前 try_claim_inflight 登记；run_duty_poll 执行结束 finally
# release。Huey 单 worker 下 tick 周期任务与 run_duty_poll 同进程，进程内登记可靠。
# 超时兜底：worker 异常/卡死导致未 release 时，陈旧登记自动失效可重新 claim，
# 避免任务被永久卡死。

# 在飞登记：{(project_id, kind): 派发时的 monotonic 时间戳}
_inflight: dict[tuple[int, str], float] = {}

# 在飞登记超时（秒）：超过该时长视为陈旧，允许重新 claim（防 worker 异常卡死）。
_INFLIGHT_TIMEOUT = 300.0


def try_claim_inflight(project_id: int, kind: str) -> bool:
    """尝试登记「(project_id, kind) 在飞」。已登记且未超时 → 返回 False（跳过投递）。

    成功登记（首次或陈旧超时重新占位）返回 True。调用方据此决定是否投递。
    """
    now = time.monotonic()
    ts = _inflight.get((project_id, kind))
    if ts is not None and now - ts < _INFLIGHT_TIMEOUT:
        return False
    _inflight[(project_id, kind)] = now
    return True


def release_inflight(project_id: int, kind: str) -> None:
    """释放「(project_id, kind)」在飞登记（run_duty_poll 结束后 finally 调用）。"""
    _inflight.pop((project_id, kind), None)


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


async def _run_duty_poll_with_release(project_id: int, kind: str | None) -> int:
    """run_duty_poll 内部实现：执行轮巡并在 finally 释放在飞登记。"""
    try:
        return await _run_duty_poll_impl(project_id=project_id, kind=kind)
    finally:
        # 执行结束（含异常）释放该 kind 的在飞登记，允许下轮 tick 正常投递。
        # kind=None 兼容旧调度（同时跑两线），两线都释放。
        if kind is None:
            release_inflight(project_id, KIND_WECOM)
            release_inflight(project_id, KIND_BUSINESS_POLL)
        else:
            release_inflight(project_id, kind)


@shared_task(name="run_duty_poll")
async def run_duty_poll(project_id: int, kind: str | None = None) -> int:
    """执行一次值守轮巡，返回处理的消息数（0 = 无新消息快速路径）。

    Args:
        kind: 指定执行种类；None 则同时执行企微线 + 业务巡检。
    """
    return await _run_duty_poll_with_release(project_id=project_id, kind=kind)


def task_is_duty(task_params: dict | None) -> bool:
    """判断 AutonomousTask 是否为值守任务（params_template 带值守标记）。"""
    if not task_params:
        return False
    return bool(task_params.get(DUTY_PARAM_MARKER))
