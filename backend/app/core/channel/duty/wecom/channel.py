"""WeComDutyChannel — 企业微信客服值守渠道。

通过收编的主系统模块（app/core/channel/duty/wecom/）实现：
- scan_all.py 全量扫描 + 可回复性分类
- read.py 读指定联系人会话
- reply.py 回复指定联系人

渠道内联调用收编模块（机制与渠道都在主系统）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.channel.base import ChannelContext, IncomingMessage
from app.core.channel.duty.base import (
    ContactDelta,
    DutyChannel,
    RawInbound,
)
from app.core.engine.message.schemas import MessageBlock
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType
from app.utils.text import chunk_text

from .read import run as read_run
from .reply import run as reply_run
from .scan_all import run as scan_all_run

logger = logging.getLogger(__name__)


@event_register()
class WeComDutyChannel(DutyChannel):
    """企业微信值守：轮巡扫描 → 增量 → 派发 Agent 处理。

    单例：@event_register() 每次实例化都会把 on_session_completed 注册到
    system_bus，非单例会重复订阅（重复发送回复）。用 __new__ 保证全局唯一。
    """

    name = "wecom_duty"

    _instance: WeComDutyChannel | None = None

    # 输出管道属性（复用语音链路 MessageBlock → 输出 Channel 的机制）：
    # Supervisor 在 route_to Worker 前输出的安抚文本会作为 AI MessageBlock
    # 经 OutputChannelPolicy 路由到 wecom_duty，这里负责把它发送到企微。
    accepts_blocks = True
    accepts_stream_events = False
    # 场景标识：source="duty"（值守场景）。policy 用场景名路由到本渠道，
    # 使「场景」（duty）与「渠道实现」（wecom）解耦。
    scenes = {"duty"}

    # 企微单条消息长度上限（实测 5201 字符被拦截；取安全余量）
    WECOM_MAX_MESSAGE_LEN = 1500

    # 企微线单次 Agent delivery 上限（秒）：HITL/长任务不至于永久钉死 worker 线程。
    # 超时后会话仍在后台跑，回复经 on_session_completed 事件到达；本轮先继续。
    DUTY_WECOM_DELIVERY_TIMEOUT = 60

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # 单例：仅实例化一次（注册事件订阅一次）。项目数据（history_dir 等）
        # 不参与单例状态，轮巡时每次按 project_id 从配置读取（§6.8.1）。
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self._initialized = True
        self._history_dir: str = ""
        self._project_id: int = 0

    def bind_project(self, cfg: dict) -> None:
        """绑定当前轮巡的项目配置（scheduler 在全局轮巡锁内调用）。

        全局轮巡锁保证同一时刻只有一个轮巡在跑，单例实例串行安全。
        history_dir 每次按项目从配置读取，不绑死首个项目（§6.8.1）。
        """
        self._history_dir = cfg.get("history_dir", "")
        self._project_id = int(cfg.get("project_id", 0) or 0)

    # ---- 输出 Channel 能力：接收 Supervisor 派活前的安抚回复 ----

    async def send(self, payload: MessageBlock, ctx: ChannelContext) -> None:
        """处理路由到 wecom_duty 的 MessageBlock（安抚回复）。

        仅处理「Supervisor 派活前」的安抚文本：AI 角色、带 route_to 工具调用
        （policy 已按此精确路由，这里再兜底校验）。直接回复/最终回复仍走
        SessionCompletedEvent 订阅，避免重复发送。
        """
        if not isinstance(payload, MessageBlock):
            return
        if payload.role != "ai":
            return
        tool_calls = payload.tool_calls or []
        names = [tc.name for tc in tool_calls if getattr(tc, "name", None)]
        if "route_to" not in names:
            return  # 非派活场景（直接回复/最终回复），走 SessionCompletedEvent
        content = (payload.content or "").strip()
        if not content:
            return
        thread_id = payload.thread_id or ctx.thread_id
        contact, project_id = self._contact_from_thread(thread_id)
        if not contact or not project_id:
            return
        logger.info(
            "[wecom_duty] 收到 Supervisor 安抚回复 (contact=%s): %r",
            contact,
            content[:50],
        )
        await self._send_reply(contact, content, project_id)

    # ---- 子类实现 ----

    async def _scan_contacts(self) -> list[ContactDelta]:
        """扫描未读 → 只取第一个有客户新消息的可回复联系人（取一条回一条）。

        只对第一个可回复联系人点开读消息（_read_customer_messages），其余
        未读联系人保持未读不触碰。返回单个 delta 或空。
        """
        result = await scan_all_run(self._history_dir)
        if result is None:
            logger.warning(
                "[wecom_duty] 企业微信未就绪或无可读未读会话（跳过本轮，下轮重试）"
            )
            return []
        replyable, _non_replyable = result
        if not replyable:
            return []

        # 取一条回一条：遍历有未读红点的可回复联系人，取第一个「有新客户消息」
        # 的（点开它读消息、处理）。已处理过（jsonl 无新增）的联系人点开后跳过，
        # 继续取下一个 —— 每次只点开当前这一个，处理完再取下一个。
        for candidate, unread_count in replyable:
            base = self.normalize_contact(candidate)
            # 该联系人已有运行中的值守会话（上轮派发未完成/HITL 等人工）→ 跳过，
            # 避免同一批消息被重复派发给 Agent。
            if self._session_alive(base):
                continue
            customer_msgs = await self._read_customer_messages(base, unread_count)
            if not customer_msgs:
                continue
            raws = [RawInbound(contact=base, text=m) for m in customer_msgs]
            logger.info("[wecom_duty] 联系人 %s 有 %d 条新客户消息", base, len(raws))
            return [ContactDelta(contact=base, raws=raws)]
        return []

    async def _read_customer_messages(self, contact: str, unread_count: int = 0) -> list[str]:
        """读取联系人的新增客户消息（收编模块内联调用）。"""
        try:
            return await read_run(self._history_dir, contact, unread_count)
        except Exception as e:
            logger.warning("[wecom_duty] 读取会话消息失败 contact=%s: %s", contact, e)
            return []

    @staticmethod
    def normalize_contact(contact: str) -> str:
        """归一化联系人名：去掉 " @微信"/"◎微信"/"®微信" 等后缀，统一用纯名。"""
        return contact.split("@")[0].split("◎")[0].split("®")[0].strip()

    def _session_alive(self, contact: str) -> bool:
        """该联系人是否已有运行中的值守会话（防同联系人重复派发）。"""
        if not self._project_id:
            return False
        thread_id = self._thread_for(self._project_id, contact)
        from app.core.engine.session.manager import session_manager

        sess = session_manager.get(thread_id)
        return sess is not None and getattr(sess, "lifecycle", None) == "running"

    async def _to_incoming(self, raw: RawInbound, project_id: int) -> IncomingMessage:
        """把一条原始客户消息归一化为 IncomingMessage（与文字链路一致）。

        source 用场景标识 "duty"（与 voice/web/mobile 并列），渠道细节放
        metadata：channel=wecom（用户可选渠道）、channel_name=wecom_duty
        （渠道实现名，供回复路由 send() 反查）。客户消息原样作为
        message_content，contact 写入 metadata 供回复路由。
        """
        return IncomingMessage(
            source="duty",
            thread_id=self._thread_for(project_id, raw.contact),
            text=raw.text,
            project_id=project_id,
            member_id=await self._duty_member_id(),
            metadata={
                "source": "duty",
                "channel": "wecom",
                "channel_name": self.name,
                "contact": raw.contact,
                "reply_to": raw.contact,
            },
        )

    async def _send_reply(self, contact: str, text: str, project_id: int = 0) -> bool:
        """发送回复到企微（收编模块内联调用，返回是否成功）。

        长回复按企微单条长度上限拆分为多段逐条发送（避免企微拦截超长消息）。
        发送成功后把回复写入该联系人 jsonl 历史（role=ai），使历史成为
        完整的客户↔客服对话记录。history_dir 按 project_id 加载（§6.8.1），
        不依赖单例实例状态（事件回调可能在轮巡结束后触发，实例 history_dir
        已被下一轮覆盖）。
        """
        chunks = chunk_text(text, WeComDutyChannel.WECOM_MAX_MESSAGE_LEN)
        if not chunks:
            return False
        sent_all = True
        for idx, chunk in enumerate(chunks):
            try:
                ok = await reply_run(contact, chunk)
            except Exception as e:
                logger.error("[wecom_duty] 发送回复失败 contact=%s: %s", contact, e)
                ok = False
            if not ok:
                sent_all = False
            if idx < len(chunks) - 1:
                import time as _time

                _time.sleep(0.5)
        if sent_all:
            try:
                from app.core.channel.duty.config import load_duty_config

                from .common import append_history

                cfg = await load_duty_config(project_id) if project_id else {}
                history_dir = cfg.get("history_dir", self._history_dir)
                append_history(history_dir, contact, chunks, role="ai")
            except Exception as e:
                logger.warning(
                    "[wecom_duty] 写入回复历史失败 contact=%s: %s", contact, e
                )
        return sent_all

    # ── 回复接收：订阅 SessionCompletedEvent（Agent 最终回复）──

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: Any) -> None:
        """接收 Agent 会话完成的最终回复（Supervisor 直接回复 / Finish 均发布）。

        从 event.data.summary 取最终回复文本，thread_id 反查联系人，脚本发送。
        """
        data = getattr(event, "data", None)
        if data is None:
            return
        thread_id = getattr(data, "thread_id", "") or ""
        if not thread_id.startswith("duty_"):
            return  # 非值守会话，跳过
        summary = (getattr(data, "summary", "") or "").strip()
        if not summary:
            return
        contact, project_id = self._contact_from_thread(thread_id)
        if not contact or not project_id:
            return
        # 仅处理本渠道（GUI）管理的会话：企微 external_userid 以 "wm" 开头，
        # 是商城微信客服（callback/MCP）渠道的会话，跳过避免重复尝试回复。
        if contact.startswith("wm"):
            return
        logger.info("[wecom_duty] 收到 Agent 最终回复 (contact=%s): %r", contact, summary[:50])
        try:
            ok = await self._send_reply(contact, summary, project_id)
            logger.info(
                "[wecom_duty] 回复发送 %s | contact=%s | 内容=%r",
                "成功" if ok else "失败",
                contact,
                summary[:50],
            )
        except Exception:
            logger.exception("[wecom_duty] 发送回复失败 contact=%s", contact)

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_business_poll_completed(self, event: Any) -> None:
        """业务巡检任务会话完成（含 HITL 被人工答复后）→ 释放 pending，允许下轮巡检。

        thread_id 格式：duty_business_{project_id}_{task_id}_{run_ts}。
        """
        data = getattr(event, "data", None)
        if data is None:
            return
        thread_id = getattr(data, "thread_id", "") or ""
        if not thread_id.startswith("duty_business_"):
            return
        rest = thread_id[len("duty_business_") :]
        pid_part, _, remaining = rest.partition("_")
        try:
            project_id = int(pid_part)
        except (ValueError, TypeError):
            return
        task_id = remaining.rsplit("_", 1)[0] if "_" in remaining else remaining
        if not task_id:
            return
        from app.core.channel.duty.base import release_business_pending

        release_business_pending(project_id, task_id)
        logger.info(
            "[wecom_duty] 业务巡检任务完成，释放 pending (project=%s, prompt=%s)",
            project_id,
            task_id,
        )

    def _contact_from_thread(self, thread_id: str) -> tuple[str, int]:
        """从值守 thread_id（duty_{project}_{contact}）解析出 (联系人, project_id)。"""
        if not thread_id.startswith("duty_"):
            return "", 0
        parts = thread_id.split("_", 2)
        if len(parts) < 3:
            return "", 0
        try:
            project_id = int(parts[1])
        except (ValueError, TypeError):
            return "", 0
        return parts[2], project_id

    async def _dispatch_safely(self, delta: ContactDelta, project_id: int) -> None:
        """按联系人统一回复：该联系人的多条新消息一次进 Agent，标准链路推理。

        与文字链路完全一致：构造 IncomingMessage → dispatch_agent_run →
        run_agent_background（Agent 引擎完整推理）。Agent 的回复通过标准
        Channel 机制（MessagePublisher → OutputChannelPolicy → wecom_duty
        渠道的 send()）异步到达，由 send() 调脚本发送到企微。
        """
        contact = delta.contact
        thread_id = self._thread_for(project_id, contact)
        lock = self._lock_for(thread_id)
        async with lock:
            try:
                # 该联系人的多条新消息合并为一条消息内容，一次送 Agent
                first = delta.raws[0]
                msg = await self._to_incoming(first, project_id)
                if len(delta.raws) > 1:
                    body = "\n".join(f"- {r.text}" for r in delta.raws)
                    msg.text = body
                result = await self.dispatch(msg)  # 基类 → dispatch_agent_run
                if result is None or getattr(result, "inputs", None) is None:
                    logger.warning(
                        "[wecom_duty] dispatch 未返回 inputs，跳过 (contact=%s)",
                        contact,
                    )
                    return
                # 标准链路：Agent 引擎完整推理（await 等 Agent 跑完，回复经事件到 send()）。
                # 统一走 session_manager.submit（与 voice/web/mobile 同一生命周期路径），
                # await_completion 保持值守"取一条回一条"的串行阻塞语义。
                from app.core.engine.session.manager import session_manager

                await session_manager.submit(
                    thread_id,
                    result.inputs,
                    await_completion=True,
                    timeout=self.DUTY_WECOM_DELIVERY_TIMEOUT,
                )
            except Exception:
                logger.exception("[%s] Failed to dispatch duty message for %s", self.name, contact)
