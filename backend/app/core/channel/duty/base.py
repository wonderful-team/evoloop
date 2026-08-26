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

logger = logging.getLogger(__name__)


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
        """业务巡检：扫描任务列表，把到期的任务逐条作为独立 human 消息发给 Agent。

        调度以 business_poll_interval（分钟）为频率扫描列表，真正的执行节奏由
        每条任务的 next_run_at + interval_minutes 控制。每条任务使用独立的
        会话（thread_id="duty_business_{project_id}_{task_id}"），彼此不共享上下文。

        返回本轮成功发送并更新 next_run_at 的任务数。
        """
        from app.core.channel.duty.config import load_duty_config, save_business_poll_prompts
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
        updated_prompts: list[dict] = []
        sent = 0

        for raw in prompts:
            if not isinstance(raw, dict):
                updated_prompts.append(raw)
                continue
            p = dict(raw)
            if not p.get("enabled", True):
                updated_prompts.append(p)
                continue
            try:
                next_dt = datetime.fromisoformat(p.get("next_run_at", ""))
                if next_dt.timestamp() > now_ts:
                    updated_prompts.append(p)
                    continue
            except (ValueError, TypeError):
                updated_prompts.append(p)
                continue

            prompt_text = (
                str(p.get("prompt") or "")
                .replace("{project_id}", str(ctx_project_id))
                .strip()
            )
            if not prompt_text:
                updated_prompts.append(p)
                continue

            # 每次巡检用独立 thread（带 run 时间戳）：业务巡检是一次性独立查证，
            # 不应共享同一条任务的历史（否则历史无限堆积、Agent 消化重复上下文）。
            task_thread_id = f"duty_business_{project_id}_{p.get('id')}_{int(now_ts)}"
            msg = IncomingMessage(
                source="duty",
                thread_id=task_thread_id,
                text=prompt_text,
                project_id=ctx_project_id,
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
                    updated_prompts.append(p)
                    continue
                from app.core.session.manager import session_manager

                session = await session_manager.submit(
                    task_thread_id, result.inputs, await_completion=False
                )

                # 派发成功即推进 next_run_at：不等 Agent 完成 delivery。
                # 否则若某条任务卡在 HITL/长任务（wait_delivery_complete 无超时
                # 永久阻塞），整轮扫描停滞，后续任务与 save_business_poll_prompts
                # 都不执行，next_run_at 永不落盘。
                interval = int(p.get("interval_minutes") or 60)
                p["next_run_at"] = (now_dt + timedelta(minutes=interval)).isoformat()
                updated_prompts.append(p)
                sent += 1
                logger.info(
                    "[duty] 业务巡检任务已发起 (project=%s, prompt=%s)",
                    project_id,
                    p.get("id"),
                )
                # delivery 完成仅作观察（带超时，best-effort），不影响调度推进
                delivered = await session.wait_delivery_complete(timeout=30)
                if not delivered:
                    logger.warning(
                        "[duty] 业务巡检任务 delivery 超时 (project=%s, prompt=%s)",
                        project_id,
                        p.get("id"),
                    )
            except Exception:
                logger.exception(
                    "[duty] 业务巡检任务失败 (project=%s, prompt=%s)",
                    project_id,
                    p.get("id"),
                )
                updated_prompts.append(p)

        await save_business_poll_prompts(project_id, updated_prompts)
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
        raise NotImplementedError("DutyChannel is poll-driven; call poll_once() instead of receive().")

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
