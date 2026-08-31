"""MpcKfChannel — 经 MCP（项目配置的 mcp_server）接入商城微信客服的值守渠道。

轮巡流程：调 ``kf_list_new_messages`` 拉未处理客户消息（direction=0 & processed=0）
→ 按 external_userid 分组 → 取一条回一条（``_dispatch_safely``）→ 读取即
``kf_mark_processed`` ack（防下轮重复拉）→ Agent 推理 → ``kf_send_text`` 回复。

与 GUI 线（``wecom/``）的差异：
- 消息自带方向/范围/未处理标记，**不需要 jsonl 增量去重**；
- 回复/历史由商城侧落库，evoloop 不写 jsonl；
- open_kfid/site_id 取自消息行，不依赖本地企微客户端。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.core.channel.base import ChannelContext, IncomingMessage
from app.core.channel.duty.base import ContactDelta, DutyChannel, RawInbound
from app.core.channel.duty.constants import (
    CHANNEL_KEY,
    DUTY_KF_DELIVERY_TIMEOUT,
    KF_PUSH_RETRY_DELAY,
    KF_TOOL_TIMEOUT,
    MAX_MESSAGE_LEN,
)
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType
from app.core.identity import identity_service
from app.utils.text import chunk_text

logger = logging.getLogger(__name__)


@event_register()
class MpcKfChannel(DutyChannel):
    """商城微信客服值守：MCP 轮巡拉新 → 派发 Agent → MCP 发送回复。

    单例：@event_register() 每次实例化都会把 on_session_completed 注册到
    system_bus，非单例会重复订阅（重复发送回复）。用 __new__ 保证全局唯一。
    """

    name = "mcp_kf"

    _instance: MpcKfChannel | None = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self._initialized = True
        self._project_id: int = 0
        self._callback_cfg: dict[str, Any] = {}
        # 经 MCP 接入的客服后端 server 名，来自项目配置 callback.mcp_server，
        # 不在代码中写死任何具体 server（MCP 接入是配置驱动的）。
        self._mcp_server: str = ""
        # contact(external_userid) → (open_kfid, site_id)，回复路由反查用
        self._kf_routing: dict[str, tuple[str, int]] = {}
        logger.debug("[mcp_kf] MpcKfChannel initialized")

    def bind_project(self, cfg: dict) -> None:
        """绑定当前轮巡的项目配置（scheduler 在全局轮巡锁内调用）。

        项目数据（callback 子配置）每次按项目读取，不绑死首个项目。
        MCP server 名从 ``callback.mcp_server`` 读取，未配置时本渠道不可用。
        """
        self._project_id = int(cfg.get("project_id", 0) or 0)
        channels = cfg.get("channels") or {}
        self._callback_cfg = channels.get(CHANNEL_KEY) or {}
        self._mcp_server = str(self._callback_cfg.get("mcp_server") or "").strip()

    # ---- 输出 Channel 能力：接收主 Agent 首个可见的安抚回复 ----
    # 本期与 GUI 线一致：安抚回复输出通道（send()）未接入 channel_registry，
    # 直接/最终回复走 SessionCompletedEvent 订阅，避免重复。

    async def send(self, payload: Any, ctx: ChannelContext) -> None:
        return

    # ---- 子类实现 ----

    async def _scan_contacts(self) -> list[ContactDelta]:
        """扫描未处理客户消息 → 只取第一个有新消息的 external_userid。

        调 ``kf_list_new_messages`` 拉未处理消息，按 external_userid 分组，
        返回第一个联系人的 delta（取一条回一条）。无新消息返回 []。
        """
        site_id = int(self._callback_cfg.get("site_id", 1) or 1)
        limit = int(self._callback_cfg.get("limit", 20) or 20)
        payload = await self._call_kf_tool(
            "kf_list_new_messages", site_id=site_id, limit=limit
        )
        if not payload:
            return []
        messages = payload.get("messages") or []
        if not messages:
            return []

        # 事件类消息（enter_session 等企微会话事件）不是客户咨询：直接 ack
        # 标记处理（防每轮重复拉取），不派发 Agent，也不参与客户分组。
        event_ids = [
            int(row["id"])
            for row in messages
            if str(row.get("msgtype") or "") == "event"
        ]
        if event_ids:
            await self._call_kf_tool(
                "kf_mark_processed", ids=",".join(str(i) for i in event_ids)
            )
            logger.info("[mcp_kf] 已标记 %d 条事件消息已处理（不派发）", len(event_ids))

        # 按 external_userid 分组（保留每条消息全量字段到 extra）
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in messages:
            if str(row.get("msgtype") or "") == "event":
                continue
            uid = str(row.get("external_userid") or "").strip()
            if not uid:
                continue
            grouped.setdefault(uid, []).append(row)

        # 取第一个有消息的联系人（保持 send_time 升序）
        first_uid = next(iter(grouped))
        rows = grouped[first_uid]
        rows.sort(key=lambda r: int(r.get("send_time", 0) or 0))
        raws = [
            RawInbound(contact=first_uid, text=self._row_text(row), extra=row)
            for row in rows
        ]
        logger.info("[mcp_kf] 联系人 %s 有 %d 条新客户消息", first_uid, len(raws))
        return [ContactDelta(contact=first_uid, raws=raws)]

    def _row_text(self, row: dict[str, Any]) -> str:
        """取一条消息的展示文本：text 用 content；媒体消息降级为带 media_path 的标注。"""
        msgtype = str(row.get("msgtype") or "text")
        if msgtype == "text":
            return str(row.get("content") or "").strip()
        media_path = str(row.get("media_path") or "").strip()
        return f"【{msgtype}】{media_path}" if media_path else f"【{msgtype}】"

    async def _to_incoming(self, raw: RawInbound, project_id: int) -> IncomingMessage:
        """把一条原始消息归一化为 IncomingMessage（与文字链路一致）。

        thread 用 ``duty_{project}_{external_userid}``。media 消息（image/voice/
        file）调 ``kf_get_media`` 取 media_path 构造 references；失败降级文本。
        """
        row = raw.extra or {}
        msgtype = str(row.get("msgtype") or "text")
        references: list[dict[str, Any]] | None = None
        if msgtype != "text":
            references = await self._media_references(row)

        kf_ids = [int(row["id"]) for row in [row] if row.get("id")]
        return IncomingMessage(
            source="duty",
            thread_id=self._thread_for(project_id, raw.contact),
            text=raw.text,
            project_id=project_id,
            member_id=await identity_service.get_member_id() or 0,
            references=references,
            metadata={
                "source": "duty",
                "channel": "mcp_kf",
                "channel_name": self.name,
                "contact": raw.contact,
                "reply_to": raw.contact,
                "external_userid": str(row.get("external_userid") or ""),
                "open_kfid": str(row.get("open_kfid") or ""),
                "site_id": int(row.get("site_id", 1) or 1),
                "kf_message_ids": kf_ids,
            },
        )

    async def _media_references(
        self, row: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        """媒体消息：调 kf_get_media 拿 media_path 构造 references（供 Agent 读取）。

        失败降级返回 None（消息以文本标注形式进 Agent，不阻断链路）。
        """
        msgtype = str(row.get("msgtype") or "file")
        media = await self._call_kf_tool("kf_get_media", id=int(row.get("id") or 0))
        media_path = str(
            (media or {}).get("media_path") or row.get("media_path") or ""
        ).strip()
        if not media_path:
            return None
        ref_type = {
            "image": "image",
            "voice": "audio",
            "file": "file",
        }.get(msgtype, "file")
        return [{"type": ref_type, "target_id": media_path}]

    async def _dispatch_safely(self, delta: ContactDelta, project_id: int) -> None:
        """按联系人统一回复：该联系人的多条新消息一次进 Agent，标准链路推理。

        读取即 ack：派发前先 ``kf_mark_processed``（商城 getUnprocessed 语义，
        防 60s 轮巡重复拉同一批消息）。代价：Agent 失败时消息已标记，靠商城
        侧补偿（客户再发消息触发新一轮）。
        """
        contact = delta.contact
        from app.core.channel.duty.scheduler import release_inflight, try_claim_inflight

        # 按客户隔离在飞：同一客户已在处理则跳过（防重复派发），不同客户互不阻塞。
        if not try_claim_inflight(project_id, f"kf:{contact}"):
            logger.info(
                "[mcp_kf] 客户 %s 的消息已在飞处理，跳过本次派发 (project=%s)",
                contact,
                project_id,
            )
            return
        try:
            thread_id = self._thread_for(project_id, contact)
            lock = self._lock_for(thread_id)
            async with lock:
                try:
                    # 记录回复路由（open_kfid/site_id 取自最新一条消息）
                    first = delta.raws[0]
                    row = first.extra or {}
                    open_kfid = str(row.get("open_kfid") or "")
                    site_id = int(row.get("site_id", 1) or 1)
                    if open_kfid:
                        self._kf_routing[contact] = (open_kfid, site_id)

                    # 读取即 ack：先标记该联系人的这批消息已处理
                    ids = [
                        int(r.extra.get("id"))
                        for r in delta.raws
                        if r.extra and r.extra.get("id")
                    ]
                    if ids:
                        await self._call_kf_tool(
                            "kf_mark_processed", ids=",".join(str(i) for i in ids)
                        )
                        logger.info(
                            "[mcp_kf] 已标记 %d 条消息已处理 (contact=%s)",
                            len(ids),
                            contact,
                        )

                    # 该联系人的多条新消息合并为一条消息内容，一次送 Agent
                    msg = await self._to_incoming(first, project_id)
                    if len(delta.raws) > 1:
                        body = "\n".join(f"- {r.text}" for r in delta.raws)
                        msg.text = body
                        msg.metadata["kf_message_ids"] = ids
                    result = await self.dispatch(msg)  # 基类 → dispatch_agent_run
                    if result is None or getattr(result, "inputs", None) is None:
                        logger.warning(
                            "[mcp_kf] dispatch 未返回 inputs，跳过 (contact=%s)",
                            contact,
                        )
                        return
                    # 标准链路：Agent 引擎完整推理（await 等 Agent 跑完，回复经事件到 send）。
                    from app.core.engine.session.manager import session_manager

                    await session_manager.submit(
                        thread_id,
                        result.inputs,
                        await_completion=True,
                        timeout=DUTY_KF_DELIVERY_TIMEOUT,
                    )
                except Exception:
                    logger.exception(
                        "[%s] Failed to dispatch duty message for %s",
                        self.name,
                        contact,
                    )
        finally:
            release_inflight(project_id, f"kf:{contact}")

    async def _send_reply(self, contact: str, text: str, project_id: int = 0) -> bool:
        """发送回复到商城微信客服（调 ``kf_send_text``），返回是否成功。

        长回复按单条长度上限拆分为多段逐条发送（避免企微拦截超长消息）。
        open_kfid/site_id 取自该联系人最近一次派发时记录的路由。
        """
        routing = self._kf_routing.get(contact)
        if not routing:
            logger.warning(
                "[mcp_kf] 联系人 %s 无回复路由（open_kfid），跳过回复", contact
            )
            return False
        open_kfid, site_id = routing

        chunks = chunk_text(text, MAX_MESSAGE_LEN)
        if not chunks:
            return False
        sent_all = True
        for idx, chunk in enumerate(chunks):
            try:
                res = await self._call_kf_tool(
                    "kf_send_text",
                    external_userid=contact,
                    open_kfid=open_kfid,
                    content=chunk,
                    site_id=site_id,
                )
                ok = bool((res or {}).get("success"))
            except Exception as e:
                logger.error("[mcp_kf] 发送回复失败 contact=%s: %s", contact, e)
                ok = False
            if not ok:
                sent_all = False
            if idx < len(chunks) - 1:
                import time as _time

                _time.sleep(0.5)
        return sent_all

    # ── MCP 工具调用封装 ──────────────────────────────────────

    async def _call_kf_tool(self, tool_name: str, **kwargs) -> dict[str, Any]:
        """调用客服后端 MCP server 的 kf 工具，解析 content[0].text 的 JSON 返回。

        server 名来自项目配置 callback.mcp_server（不在代码写死）。工具未配置 /
        未注册 / 调用失败 / 返回非 JSON → logger.warning + 返回 {}（轮巡对外部
        服务瞬时故障容忍，但不静默：必须留日志）。调用本身有超时兜底，
        防远程 MCP 会话僵死时无限挂起。
        """
        from app.core.mcp.client.manager import mcp_client_manager

        server = self._mcp_server
        if not server:
            logger.warning(
                "[mcp_kf] 项目未配置 callback.mcp_server，MCP 客服渠道不可用"
            )
            return {}
        tools = await mcp_client_manager.get_tools(server)
        if not tools:
            logger.warning("[mcp_kf] MCP server %s 未连接或无工具", server)
            return {}
        full_name = f"mcp__{server.replace('-', '_').lower()}__{tool_name}"
        tool = next((t for t in tools if t.name == full_name), None)
        if tool is None:
            logger.warning("[mcp_kf] 工具 %s 不在 %s 上", full_name, server)
            return {}
        try:
            result = await asyncio.wait_for(
                tool.func(**kwargs),
                timeout=KF_TOOL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[mcp_kf] 调用 %s 超时(>%ss)，跳过（外部 MCP 僵死不能阻塞值守）",
                full_name,
                KF_TOOL_TIMEOUT,
            )
            return {}
        except Exception as e:
            logger.warning("[mcp_kf] 调用 %s 失败: %s", full_name, e, exc_info=True)
            return {}
        return self._parse_tool_result(result)

    @staticmethod
    def _parse_tool_result(result: Any) -> dict[str, Any]:
        """把 CallToolResult 的 text content 解析为 dict；失败返回 {}。"""
        try:
            content = getattr(result, "content", None) or []
            for c in content:
                text = getattr(c, "text", None)
                if text:
                    decoded = json.loads(text)
                    if isinstance(decoded, dict):
                        return decoded
        except (ValueError, TypeError, json.JSONDecodeError):
            logger.warning(
                "[mcp_kf] 工具返回非 JSON，忽略: %r",
                getattr(result, "content", None)[:120],
            )
        return {}

    # ── 回复接收：订阅 SessionCompletedEvent（Agent 最终回复）──

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: Any) -> None:
        """接收 Agent 会话完成的最终回复（主 Agent 最终回应）。

        从 event.data.summary 取最终回复文本，thread_id 反查联系人，MCP 发送。
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
        # 只处理本渠道的会话：contact 必须是 external_userid（在 _kf_routing 里）
        if contact not in self._kf_routing:
            return
        logger.info(
            "[mcp_kf] 收到 Agent 最终回复 (contact=%s): %r", contact, summary[:50]
        )
        try:
            ok = await self._send_reply(contact, summary, project_id)
            logger.info(
                "[mcp_kf] 回复发送 %s | contact=%s | 内容=%r",
                "成功" if ok else "失败",
                contact,
                summary[:50],
            )
        except Exception:
            logger.exception("[mcp_kf] 发送回复失败 contact=%s", contact)

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

    @event_subscribe(SystemEventType.MCP_SERVER_NOTIFICATION)
    async def on_kf_new_message(self, event: Any) -> None:
        """收到线上 MCP 推送的 kf_new_message 通知 → 立即触发本渠道轮巡。

        替代等待 60s 定时轮巡，实现秒级响应。project_id 取当前绑定项目；
        未绑定（0）时跳过，交由定时轮巡兜底。仅处理本渠道（项目配置的
        callback.mcp_server）推送的 kf_new_message，其余 server/通知忽略。
        """
        server_name = getattr(event, "server_name", "") or ""
        data = getattr(event, "data", None)
        method = getattr(data, "method", "") if data is not None else ""
        if not self._mcp_server or server_name != self._mcp_server:
            return
        if "kf_new_message" not in str(method):
            return
        project_id = int(getattr(self, "_project_id", 0) or 0)
        if project_id <= 0:
            logger.info("[mcp_kf] KF_NEW_MESSAGE 通知到达，但未绑定项目，跳过")
            return
        logger.info(
            "[mcp_kf] 收到 KF_NEW_MESSAGE 推送，立即轮巡 (project=%s)", project_id
        )
        try:
            from app.core.channel.duty.scheduler import (
                KIND_KF,
                run_duty_poll_with_release,
            )

            # 值守轮巡不进持久队列：进程内直接执行（避免队列残留旧任务）。
            handled = await run_duty_poll_with_release(
                project_id=project_id, kind=KIND_KF
            )
            # 远程 servicer 推送 kf_new_message 后经常紧接着关闭 SSE 连接
            # （"推送即断"），此时立即轮巡会打到退化会话上、kf_list 超时返回空。
            # 等一拍（覆盖 keepalive 重连窗口），再补一次轮巡兜底。
            if handled <= 0:
                logger.info(
                    "[mcp_kf] 推送后首次轮巡未拉到消息，%ss 后补轮巡兜底",
                    KF_PUSH_RETRY_DELAY,
                )
                await asyncio.sleep(KF_PUSH_RETRY_DELAY)
                await run_duty_poll_with_release(project_id=project_id, kind=KIND_KF)
        except Exception:
            logger.exception(
                "[mcp_kf] KF_NEW_MESSAGE 触发轮巡异常 project=%s", project_id
            )
