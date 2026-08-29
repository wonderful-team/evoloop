"""DutyChannel — 客服值守渠道基类（渠道无关的通用值守机制）。

值守与普通消息渠道（Web/voice/mobile）的本质区别：
1. 主动轮巡拉取（时间驱动），而非被动接收
2. 多客户、多 thread（每个联系人独立），非单会话
3. 增量去重（以 jsonl 历史文本为基准），非天然幂等
4. 回复动态路由（谁发消息回谁）

子类只需实现三个渠道特有的方法：
- ``_scan_contacts``：遍历会话，返回有新增且可回复的联系人
- ``_to_incoming``：原始消息 → IncomingMessage
- ``_send_reply``：向指定联系人发送回复

基类封装：快速路径、多联系人 thread + 锁、回复路由元数据。
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.channel.base import IncomingMessage, InputChannel
from app.core.identity import identity_service

logger = logging.getLogger(__name__)

# 业务巡检"在审/等待"登记（进程内）：{(project_id, task_id): thread_id}
# 任务派发后若 Agent 进入 HITL 等待人工，会话仍存活 → 该任务标记为 pending，
# 下轮扫描跳过，避免同一批待办被反复巡检、HITL 请求堆积。会话真正完成
# （SESSION_COMPLETED）后由 release_business_pending 清除，下轮才可重新巡检。
# 单 worker 进程内有效：重启后清空，下轮扫描重新派发（可接受）。
_BUSINESS_PENDING: dict[tuple[int, str], str] = {}


def release_business_pending(project_id: int, task_id: str) -> None:
    """业务巡检任务会话完成（SESSION_COMPLETED）后释放 pending。"""
    _BUSINESS_PENDING.pop((project_id, task_id), None)


def is_business_pending(project_id: int, task_id: str) -> bool:
    """该任务是否处于"在审/等待"（上一轮已派发且会话仍存活）。"""
    thread_id = _BUSINESS_PENDING.get((project_id, task_id))
    if not thread_id:
        return False
    from app.core.engine.session.manager import session_manager

    sess = session_manager.get(thread_id)
    return sess is not None and getattr(sess, "lifecycle", None) == "running"


@dataclass
class RawInbound:
    """渠道原始消息（子类扫描产生）。"""

    contact: str  # 联系人（thread 维度）
    text: str  # 消息文本
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContactDelta:
    """单个联系人的新增消息集合。"""

    contact: str
    raws: list[RawInbound] = field(default_factory=list)


class DutyChannel(InputChannel, ABC):
    """值守渠道基类：封装快速路径、多联系人 thread、回复路由。"""

    name: str = "duty"

    # —— 子类必须实现：渠道特有的"全量扫描拉取" ——

    @abstractmethod
    async def _scan_contacts(self) -> list[ContactDelta]:
        """遍历所有会话，返回"有新增消息且可回复"的联系人 + 各自新增原始消息。

        只处理 REPLYABLE 联系人（能回复的客户），NON_REPLYABLE（服务号推送）跳过。
        每个联系人的 raws 只含该渠道识别为「新增」的消息（增量判定由渠道实现，
        通常以 jsonl 历史文本为基准）。
        """

    @abstractmethod
    async def _to_incoming(self, raw: RawInbound) -> IncomingMessage:
        """把一条原始消息归一化为 IncomingMessage（含 contact 元数据）。"""

    @abstractmethod
    async def _send_reply(self, contact: str, text: str) -> bool:
        """向指定联系人发送回复（映射宏 1451 或渠道脚本）。返回是否发送成功。"""

    # —— 基类实现的通用值守机制 ——

    def __init__(self) -> None:
        # 每联系人 thread 的锁（同联系人串行，不同联系人并发）
        self._thread_locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, thread_id: str) -> asyncio.Lock:
        """获取（或创建）某联系人 thread 的锁。"""
        lock = self._thread_locks.get(thread_id)
        if lock is None:
            lock = asyncio.Lock()
            self._thread_locks[thread_id] = lock
        return lock

    @staticmethod
    def _thread_for(project_id: int, contact: str) -> str:
        """每个联系人独立 thread，跨轮巡持久，与操作者会话隔离。"""
        return f"duty_{project_id}_{contact}"

    async def poll_once(self, project_id: int) -> int:
        """单次轮巡：取一条回一条，连续处理完所有有未读的联系人。

        每次 _scan_contacts 只返回「第一个有未读的联系人」（点开它取消息、
        处理、回复），完成后再次扫描取下一条 —— 取消息与处理交织，绝不
        预先遍历所有联系人点开会话（否则会清掉所有未读）。返回处理的消息数。
        """
        handled = 0
        while True:
            # 取一个联系人（只点开这一个，读它的新消息）
            delta = await self._scan_contacts_one()
            if delta is None:
                break
            # 该联系人的新消息统一送 Agent 处理并回复
            await self._dispatch_safely(delta, project_id)
            handled += len(delta.raws)
        return handled

    async def business_poll_check(self, project_id: int) -> int:
        """业务巡检：扫描任务列表，先"认领"所有到期任务，再**串行**逐条派发给 Agent。

        调度以 business_poll_interval（分钟）为频率扫描列表，真正的执行节奏由
        每条任务的 next_run_at + interval_minutes 控制。每条任务使用独立的
        会话（thread_id="duty_business_{project_id}_{task_id}"），彼此不共享上下文。

        **认领即推进**：扫描一开始，把所有「到期 + 启用 + 未在飞」的任务统一推进
        next_run_at 并立即落盘完整列表——即使进程被强杀/重启，这些任务都已标记为
        "已调度"，**一个都不重跑**（"进程停止，任务就停止"），也不截断配置。

        **串行派发**：对已认领的任务一次只派一条，`await wait_delivery_complete()`
        等它完成（含 HITL 被人工答复）才派下一条——同一时刻只有一个巡检 Agent 在跑，
        不并发抢浏览器。HITL 挂起时该任务保持 pending、不误判为完成。
        串行期间 scheduler 的 _active_kinds[KIND_BUSINESS_POLL] 保持占用，阻止再次进入。

        返回本轮成功发送并更新 next_run_at 的任务数。
        """
        from app.core.channel.duty.config import (
            load_duty_config,
            save_business_poll_prompts,
        )
        from app.core.state import shared_state

        cfg = await load_duty_config(project_id)
        prompts = cfg.get("business_poll_prompts") or []
        if not prompts:
            return 0

        # 项目上下文以 shared_state 为准（SSOT，与 web/voice/mobile 入口一致）
        current_project_id = await shared_state.get_active_project_id()
        ctx_project_id = current_project_id or project_id

        now_dt = datetime.now(timezone.utc)
        now_ts = now_dt.timestamp()
        sent = 0
        # 巡检会话归属操作者（解析一次，整轮复用），使其出现在前台会话列表
        duty_member_id = await identity_service.get_member_id() or 0

        # ── 1. 认领 pass：把本轮所有到期任务先推进 next_run_at 并落盘 ──
        claimed: list[int] = []
        for i, raw in enumerate(prompts):
            if not isinstance(raw, dict):
                continue
            p = raw
            if not p.get("enabled", True):
                continue
            try:
                next_dt = datetime.fromisoformat(p.get("next_run_at", ""))
                if next_dt.timestamp() > now_ts:
                    continue
            except (ValueError, TypeError):
                continue
            # pending：上一轮已派发、会话仍在跑（含 HITL 等人工）→ 本轮不认领、不派发
            if is_business_pending(project_id, str(p.get("id") or "")):
                logger.info(
                    "[duty] 业务巡检任务 pending，等待上一轮完成 (project=%s, prompt=%s)",
                    project_id,
                    p.get("id"),
                )
                continue
            interval = int(p.get("interval_minutes") or 60)
            prompts[i]["next_run_at"] = (
                now_dt + timedelta(minutes=interval)
            ).isoformat()
            claimed.append(i)

        if claimed:
            # 认领即落盘完整列表：进程被强杀/重启后，这些任务都已推进，不重跑
            await save_business_poll_prompts(project_id, prompts)

        # ── 2. 串行派发已认领的任务 ──
        for i in claimed:
            p = prompts[i]
            prompt_text = (
                (p.get("prompt") or "")
                .replace("{project_id}", str(ctx_project_id))
                .strip()
            )
            if not prompt_text:
                continue

            # 每次巡检用独立 thread（带 run 时间戳）：业务巡检是一次性独立查证
            task_thread_id = f"duty_business_{project_id}_{p.get('id')}_{int(now_ts)}"
            msg = IncomingMessage(
                source="duty",
                thread_id=task_thread_id,
                text=prompt_text,
                project_id=ctx_project_id,
                member_id=duty_member_id,
                metadata={"source": "duty", "channel_name": self.name},
            )
            try:
                result = await self.dispatch(msg)
                if result is None or getattr(result, "inputs", None) is None:
                    logger.warning(
                        "[duty] 业务巡检任务 dispatch 未返回 inputs，跳过 (project=%s, prompt=%s)",
                        project_id,
                        p.get("id"),
                    )
                    continue
                from app.core.engine.session.manager import session_manager

                session = await session_manager.submit(
                    task_thread_id, result.inputs, await_completion=False
                )

                sent += 1
                _BUSINESS_PENDING[(project_id, str(p.get("id") or ""))] = task_thread_id
                logger.info(
                    "[duty] 业务巡检任务已发起 (project=%s, prompt=%s)",
                    project_id,
                    p.get("id"),
                )

                # 串行：等这条 delivery 完成（含 HITL 被人工答复）才派下一条。
                # 会话被停止/关闭（_close_session 触发 delivery 通知）也会让这里返回。
                await session.wait_delivery_complete()
            except Exception:
                logger.exception(
                    "[duty] 业务巡检任务失败 (project=%s, prompt=%s)",
                    project_id,
                    p.get("id"),
                )

        # 兜底落盘完整列表（保留 enabled/disabled 等字段与已推进的 next_run_at）
        if claimed:
            await save_business_poll_prompts(project_id, prompts)
        return sent

    async def _scan_contacts_one(self) -> ContactDelta | None:
        """取「第一个有未读的可回复联系人」及其新消息（取一条回一条）。

        只点开这一个联系人读消息（识别/过滤/增量在渠道实现），返回它的
        新消息 delta；无未读则返回 None。
        """
        deltas = await self._scan_contacts()
        if not deltas:
            return None
        return deltas[0]

    @abstractmethod
    async def _scan_contacts(self) -> list[ContactDelta]:
        """扫描未读，返回当前第一个有新增消息的联系人及其新消息。

        每次只返回一个（或空）。取消息时只点开这一个联系人会话，
        其余未读联系人保持未读不触碰。
        """

    @abstractmethod
    async def _dispatch_safely(self, delta: ContactDelta, project_id: int) -> None:
        """按联系人统一回复：该联系人的多条新消息一次进 Agent（标准链路）。

        由子类实现：构造 IncomingMessage → dispatch_agent_run →
        run_agent_background。Agent 回复经标准 Channel 机制（send()）到达。
        """

    # InputChannel.receive 不适用于主动轮巡，置为显式不可用
    async def receive(self, raw: Any, **kwargs: Any) -> IncomingMessage | None:  # type: ignore[override]
        raise NotImplementedError(
            "DutyChannel is poll-driven; call poll_once() instead of receive()."
        )

    # 值守渠道被注册为输出 channel（安抚回复 send()），HITL 请求无交互 UI，
    # 显式 no-op（与 VoiceChannel 同语义：HITL 以状态变化呈现，不推送）。
    async def send_hitl_request(
        self,
        request_id: str,
        request_type: str,
        prompt: str,
        ctx: Any,
        options: list[str] | None = None,
        context: str | None = None,
        default_value: str | None = None,
        tool_name: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        return
