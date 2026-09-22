"""
HITL orchestrator: detection, normalization, state closure, and authorization.

Previously located in app.core.engine.hitl.
"""

import json
import logging
import os

from sqlalchemy import select

from app.core.engine.message.constants import MessageStatus
from app.core.hitl.activity_sink import get_activity_sink
from app.core.hitl.constants import (
    DEFAULT_AUTHORIZATION_TTL_DAYS,
    DEFAULT_GRANTED_BY,
    MESSAGE_CATEGORY_HITL_REQUEST,
)
from app.core.hitl.core import (
    HumanInputRequest,
    create_request,
    push_hitl_notification,
    raise_hitl_interrupt,
)
from app.core.hitl.engine_runtime import get_runtime
from app.core.hitl.types import HITLDecision, HITLRequestStatus, HumanRequestType
from app.i18n.service import i18n
from app.infrastructure.database import session_scope
from app.models import Message
from app.utils.id import gen_uuid
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


async def get_pending_hitl_call(config: dict) -> dict | None:
    """
    Detects a pending HITL request from the Message table.
    Returns the tool_call dictionary if found, otherwise None.
    """
    try:
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            async with session_scope() as session:
                stmt = (
                    select(Message)
                    .where(
                        Message.thread_id == thread_id,
                        Message.role == "system",
                        Message.category == MESSAGE_CATEGORY_HITL_REQUEST,
                        Message.status == MessageStatus.WAITING_HUMAN,
                    )
                    .order_by(Message.sequence_number.desc())
                )
                res = await session.execute(stmt)
                last_hitl = res.scalars().first()

                if last_hitl and last_hitl.meta_data:
                    original = last_hitl.meta_data.get("original_tool") or {}
                    t_name = original.get("name") or last_hitl.tool_name
                    request_id = last_hitl.meta_data.get("hitl_request_id")
                    # tool_call_id 对称：写入端 fallback 为 request_id（core.py
                    # push 时 ``tool_call_id or request_id``），读取端必须用相同
                    # fallback，否则 tool_call_id 为空时 close 永远匹配不到消息。
                    t_call_id = last_hitl.tool_call_id or request_id
                    t_args = original.get("args") or {}
                    authorization = last_hitl.meta_data.get("authorization") or {}
                    # 从消息 content（JSON，含 type）解析 request_type，供 resume
                    # 端决定是否需要 APPROVED/REJECTED 归一化（ask_human text 等
                    # 类型必须保留原始文本）。
                    request_type = None
                    if last_hitl.content:
                        try:
                            parsed_content = json.loads(last_hitl.content)
                            request_type = (
                                parsed_content.get("type")
                                if isinstance(parsed_content, dict)
                                else None
                            )
                        except (json.JSONDecodeError, TypeError):
                            request_type = None
                    if t_name and t_call_id:
                        logger.info(
                            f"[HITL] Located pending authorization request for "
                            f"{t_name} ({t_call_id}) from Message table."
                        )
                        return {
                            "id": t_call_id,
                            "name": t_name,
                            "args": t_args,
                            "request_id": request_id,
                            "request_type": request_type,
                            # authorization 元数据（resource_path/action）标记这是
                            # 授权门控工具，审批后应重执行而非仅回显 APPROVED。
                            "authorization": authorization if authorization else None,
                            # resume 元数据：发起端声明的重执行豁免（args/config
                            # 注入），见 core.push_hitl_notification。
                            "resume": last_hitl.meta_data.get("resume"),
                            "project_id": last_hitl.project_id,
                        }
    except Exception as e:
        logger.warning(f"Failed to find pending HITL call: {e}", exc_info=True)

    return None


# 已知的自由文本请求类型：用户输入原样透传，不做 APPROVED/REJECTED 归一化。
_FREE_TEXT_REQUEST_TYPES = frozenset(
    {
        HumanRequestType.TEXT.value,
        HumanRequestType.CHOICE.value,
        HumanRequestType.MULTI_CHOICE.value,
        HumanRequestType.PROJECT_SWITCH.value,
        HumanRequestType.FILE_SELECT.value,
    }
)
# 批准/拒绝同义词（中英文，仅 approval 类请求下生效）。
_APPROVAL_SYNONYMS = frozenset(
    {
        "yes",
        "approve",
        "approved",
        "confirm",
        "ok",
        "y",
        "同意",
        "确认",
        "批准",
        "允许",
        "可以",
        "好的",
        "好",
        "是",
        "行",
    }
)
_REJECTION_SYNONYMS = frozenset(
    {
        "no",
        "reject",
        "rejected",
        "cancel",
        "cancelled",
        "deny",
        "n",
        "拒绝",
        "不同意",
        "取消",
        "不行",
        "否",
    }
)


def normalize_hitl_input(
    tool_call: dict, user_input: str | None, request_type: str | None = None
) -> str:
    """
    Normalizes raw user input into a format expected by approval-style HITL tools
    (``confirmation`` / ``approval``, incl. authorization-gated tools): converts
    "yes" -> "APPROVED", "no" -> "REJECTED".

    For free-text request types (``text``, ``choice``, ``project_switch``,
    ``file_select``) the user's input is returned verbatim — "yes"/"no" are
    legitimate text answers and must NOT be coerced into approval tokens.

    Empty/None input resolves to ``REJECTED`` (fail-safe): the frontend always
    sends an explicit ``"yes"``/``"no"`` (or free text), so a blank response
    means no explicit approval — it must never silently approve a sensitive
    authorization-gated operation.

    When ``request_type`` is missing or unknown (e.g. legacy pending requests),
    the tool's ``name`` and ``authorization`` metadata are used as a fallback:
    authorization-gated tools and standard confirmation tools still normalize.
    """
    if request_type in (
        HumanRequestType.CONFIRMATION.value,
        HumanRequestType.APPROVAL.value,
    ):
        is_approval = True
    elif request_type in _FREE_TEXT_REQUEST_TYPES:
        is_approval = False
    else:
        # 未知/缺失 request_type：退回按授权标记/框架工具名判定（授权门控请求必然
        # 携带 authorization 元数据；run_macro 等业务工具确认同样携带，无需列名）。
        is_approval = None

    if is_approval is None:
        name = (
            (tool_call.get("name") or "").lower() if isinstance(tool_call, dict) else ""
        )
        is_approval = bool(tool_call.get("authorization")) or name in (
            "ask_confirm",
            "request_approval",
        )

    if not is_approval:
        # 自由文本类型：原样返回（含空输入——文本输入可能合法为空）
        return user_input if user_input is not None else ""

    if not user_input or not user_input.strip():
        return HITLDecision.REJECTED.value  # Fail-safe: no explicit input = no approval

    lower_input = user_input.lower().strip()

    # Universal approval/rejection normalization (covers authorization-style HITL
    # where the original blocked tool name is not a standard HITL tool).
    if lower_input in _APPROVAL_SYNONYMS:
        return HITLDecision.APPROVED.value
    if lower_input in _REJECTION_SYNONYMS:
        return HITLDecision.REJECTED.value

    return user_input


async def close_hitl_message(
    thread_id: str, tool_call_id: str, status: str = MessageStatus.COMPLETED
) -> None:
    """
    Update the status of the HITL request message in the database (single-track).

    Unlike ``finalize_request`` (which atomically updates both the
    ``human_requests`` and ``messages`` tracks), this only closes the message
    track. Used by the A2A callback path which never created a human_request
    row (its HITL request came from ``task`` 工具的 A2A remote 委派)。
    """
    try:
        success = await get_runtime().close_hitl_message(
            thread_id, tool_call_id, status
        )
        if success:
            logger.debug(f"HITL message {tool_call_id} closed as {status}")
        else:
            logger.warning(
                f"Failed to find HITL message for tool_call_id: {tool_call_id}"
            )
    except Exception as e:
        logger.exception(f"Error closing HITL message: {e}")


class HITLOrchestrator:
    """
    Unified orchestrator for Human-In-The-Loop interactions.
    Handles detection, normalization, state closure, and authorization.
    """

    @staticmethod
    async def get_pending_request(thread_id: str, model: str) -> dict | None:
        """Standardized detection of pending HITL calls from the Message table."""
        config = {"configurable": {"thread_id": thread_id, "model": model}}
        return await get_pending_hitl_call(config)

    @staticmethod
    async def raise_approval(
        *,
        thread_id: str,
        prompt: str,
        context: str,
        tool_name: str,
        risk_level: str,
        tool_call_id: str | None = None,
        parent_id: str | None = None,
        project_id: int | None = None,
        run_id: str | None = None,
        original_tool_name: str | None = None,
        original_tool_args: dict | None = None,
        skip_grant: bool = False,
        action: str | None = None,
        resource_path: str | None = None,
        response_template: str | None = None,
        response_text_factory=None,
        resume_override: dict | None = None,
    ) -> str:
        """统一发起 approval 请求：create_request → push_hitl_notification →
        raise_hitl_interrupt。

        消除 ask_confirm / run_macro 确认 / MCP 写工具确认各自重复的
        "create + push + raise" 三步。返回中断消息文本（``response_text``）。

        ``response_template`` 用于自定义"请求已发起"的提示（含 ``{id}`` 与
        ``{prompt}`` 占位）；``response_text_factory`` 接收 ``HumanInputRequest``
        返回完整响应文本（如 ask_confirm 用 i18n 模板展示完整上下文）。
        两者都不传则用默认文案。

        ``resume_override``：审批后重执行的门控豁免声明（``{"args": {...}}``），
        随请求元数据下发，resume 端按声明注入，不在编排层按工具名特判。
        """
        from app.core.hitl.core import create_request, push_hitl_notification

        request = await create_request(
            thread_id=thread_id,
            request_type=HumanRequestType.APPROVAL.value,
            prompt=prompt,
            context=context,
            default_value=HITLDecision.REJECTED.value,
            resource_path=resource_path,
            resource_action=action,
        )

        if response_text_factory is not None:
            response_text = response_text_factory(request)
        elif response_template:
            # 不能直接 .format()：宏名/指令可能含 {query} 等花括号模板，
            # str.format 会误当占位符抛 KeyError（如宏『完成退款{query}』）。
            # 只精确替换 {id}/{prompt}，其它花括号原样保留。
            response_text = response_template.replace("{id}", request.id).replace(
                "{prompt}", prompt
            )
        else:
            response_text = i18n.get("hitl.approval_default", id=request.id)

        await push_hitl_notification(
            thread_id=thread_id,
            request=request,
            request_data={
                "id": request.id,
                "type": HumanRequestType.APPROVAL.value,
                "prompt": prompt,
                "context": context,
                "default_value": HITLDecision.REJECTED.value,
                "risk_level": risk_level,
            },
            project_id=project_id,
            run_id=run_id,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            parent_id=parent_id,
            original_tool_name=original_tool_name,
            original_tool_args=original_tool_args,
            resource_path=resource_path,
            action=action,
            skip_grant=skip_grant,
            resume_override=resume_override,
        )

        raise_hitl_interrupt(request.id, response_text)
        return response_text  # unreachable

    @staticmethod
    async def handle_resume(
        thread_id: str, tool_call: dict, user_input: str | None, grant_mode: str | None = None
    ) -> tuple[str, bool]:
        """Processes resume logic: normalization, atomic dual-track closure, activity cleanup.

        Returns ``(normalized_input, claimed)``：``claimed=False`` 表示并发场景下
        本请求已被其他端（手机/桌面/CLI）抢先消费——调用方必须跳过重执行与
        agent 恢复，避免同一工具被执行两次（副作用×2）。
        """
        from app.core.hitl.core import finalize_request

        normalized = normalize_hitl_input(
            tool_call, user_input, request_type=tool_call.get("request_type")
        )
        request_id = tool_call.get("request_id")
        # 原子化关闭两轨（human_requests + messages），避免半关闭。
        # 同工具+同参数的兄弟 pending 请求一并关闭（Agent 重试可能产生重复
        # approval 请求，见 handoff mcp-confirm-gap §3.4 残留问题）。
        sibling_key = {
            "name": tool_call.get("name"),
            "args": tool_call.get("args") or {},
        }
        claimed = await finalize_request(
            thread_id=thread_id,
            request_id=request_id,
            tool_call_id=tool_call["id"],
            status=MessageStatus.COMPLETED,
            response=normalized,
            sibling_key=sibling_key,
        )
        await get_activity_sink().clear_human_request(thread_id)
        return normalized, claimed

    @staticmethod
    async def handle_cancel(thread_id: str, tool_call: dict) -> str:
        """Processes cancellation logic: atomic dual-track closure, activity cleanup."""
        from app.core.hitl.core import finalize_request

        request_id = tool_call.get("request_id")
        # 取消时同工具+同参数的兄弟 pending 请求一并取消，避免残留。
        sibling_key = {
            "name": tool_call.get("name"),
            "args": tool_call.get("args") or {},
        }
        await finalize_request(
            thread_id=thread_id,
            request_id=request_id,
            tool_call_id=tool_call["id"],
            status=MessageStatus.CANCELLED,
            sibling_key=sibling_key,
        )
        await get_activity_sink().clear_human_request(thread_id)
        return HITLDecision.CANCELLED.value

    @staticmethod
    async def persist_hitl_user_message(
        thread_id: str,
        project_id: int | None,
        member_id: int,
        tool_call_id: str,
        user_content: str | None,
        final_result: str,
    ) -> None:
        """把 HITL 用户答复落为 human 消息，并更新原 tool 消息结果（而非新增）。

        - ``human`` 消息：让用户在会话里看到自己的选择/输入（choice/text 为
          原文，approval 类为 APPROVED/REJECTED），前端据此渲染用户气泡。
        - 更新原 ask_human / 授权工具的 tool 消息内容为最终结果，而不是新增
          一条 tool 消息——否则同一 tool_call 出现两条 tool 结果，LLM 重建
          上下文会取到空的旧 tool_output（HITL 选项未被 Agent 消费的问题）。

        实现位于 engine runtime（``EngineRuntime.persist_hitl_user_message``），
        编排层只负责领域语义，不反向依赖 message 子系统。
        """
        await get_runtime().persist_hitl_user_message(
            thread_id=thread_id,
            project_id=project_id,
            member_id=member_id,
            tool_call_id=tool_call_id,
            user_content=user_content,
            final_result=final_result,
        )

    @staticmethod
    async def resume_and_persist(
        thread_id: str,
        project_id: int | None,
        member_id: int,
        config: dict,
        user_input: str | None,
        state=None,
        grant_mode: str | None = None,
    ) -> bool:
        """统一的后台/会话恢复路径：检测 → 关闭请求 → 审批重执行 → 持久化。

        供 ``runner.py``（voice/background）与 ``session.py``（会话模式）复用，
        消除两处几乎相同的 "handle_resume + resolve_approved_tool_result +
        repo.persist" 重复逻辑。返回是否确实消费了 pending 请求。

        注意：``chat.py`` 的单发（无会话）路径刻意不走这里——它把工具结果写回
        ``inputs.messages``，交给后台 react 循环消费，而非独立 persist。
        """
        pending_tool = await HITLOrchestrator.get_pending_request(
            thread_id, (config.get("configurable") or {}).get("model")
        )
        if not pending_tool:
            return False
        normalized_input, claimed = await HITLOrchestrator.handle_resume(
            thread_id, pending_tool, user_input, grant_mode=grant_mode
        )
        if not claimed:
            # 并发 resume 竞态：pending 已被其他端消费，重执行由消费方负责。
            logger.info(
                "[HITL] resume lost race for pending request (thread=%s, call=%s) — skip re-execution",
                thread_id,
                pending_tool.get("id"),
            )
            return False
        final_result = await HITLOrchestrator.resolve_approved_tool_result(
            pending_tool,
            config,
            normalized_input,
            state=state,
            grant_mode=grant_mode,
            thread_id=thread_id,
        )
        # 落为 human 消息（用户可见）+ 更新原 tool 消息结果（Agent 可见），
        # 而非新增 tool 消息（避免同 tool_call 双 tool 结果导致 Agent 取空）。
        # 用户可见文案按"点了什么存什么"：中文界面落中文（批准/拒绝），英文界面
        # 落英文（Approve/Reject）；normalized 只用于内部决策（APPROVED/REJECTED）。
        await HITLOrchestrator.persist_hitl_user_message(
            thread_id=thread_id,
            project_id=project_id,
            member_id=member_id,
            tool_call_id=pending_tool["id"],
            user_content=user_input or normalized_input,
            final_result=final_result,
        )
        return True

    @staticmethod
    async def resolve_approved_tool_result(
        pending_tool: dict,
        config: dict,
        fallback_result: str,
        state=None,
        grant_mode: str | None = None,
        thread_id: str | None = None,
    ) -> str:
        """审批后的工具结果：授权门控工具记录授权并重执行，返回真实结果；否则回退。

        对 confirmation 类工具，``APPROVED`` 就是答案（``fallback_result``）。
        对 authorization 门控工具（``pending_tool["authorization"]`` 存在），
        审批后必须用原始参数重执行工具——否则工具会被标记完成但从未执行
        （副作用缺失，Agent 却报告成功）。

        ⚠ ``REJECTED``（拒绝访问）：直接返回拒绝结果，**不授予权限、不重执行**。
        用户拒绝即不授权，任何后续访问都应继续走 HITL。
        """
        tool_name = pending_tool.get("name")
        tool_args = pending_tool.get("args") or {}
        tool_call_id = pending_tool.get("id")

        authorization = pending_tool.get("authorization") or {}
        # 授权目标单一事实源：authorization.all_paths（含首路径）是权威列表；
        # 旧数据（迁移前创建的 pending）无 all_paths 时回退单路径。
        all_paths: list[tuple[str, str]] = []
        for entry in authorization.get("all_paths") or []:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                all_paths.append((str(entry[0]), str(entry[1])))
        if not all_paths and authorization.get("resource_path"):
            all_paths = [
                (authorization["resource_path"], authorization.get("action", "read"))
            ]

        # 自由文本类型（无 authorization）：原样返回用户输入，不触发任何
        # APPROVED/REJECTED 判定——"REJECTED" 作为文本输入是合法内容。
        if not authorization:
            # 确认/审批类被拒绝：返回描述性本地化文案（而非裸 REJECTED 标记），
            # 让 Agent 明确知道"操作未执行、应终止并汇报"，避免偏离主题另起炉灶。
            # 仅 approval/confirmation 类生效；自由文本类（text/choice/multi_choice
            # /project_switch/file_select）里 "REJECTED" 是合法文本，必须原样透传。
            request_type = pending_tool.get("request_type")
            is_approval = request_type in (
                HumanRequestType.CONFIRMATION.value,
                HumanRequestType.APPROVAL.value,
            )
            # 未知/缺失 request_type（legacy pending）：退回按工具名启发式判定
            # （与 normalize_hitl_input 的 fallback 一致）。
            if request_type is None:
                name = (tool_name or "").lower()
                is_approval = name in ("ask_confirm", "request_approval")
            if (
                is_approval
                and isinstance(fallback_result, str)
                and fallback_result.upper() == HITLDecision.REJECTED.value
            ):
                return i18n.get("hitl.operation_rejected", tool=tool_name or "")
            return fallback_result

        # 用户拒绝（授权门控）：不授权、不重执行，返回明确拒绝说明。
        # CorrectedError 语义（对齐 OpenCode）：让模型知道该操作被拒、未执行、
        # 不要重试，避免偏离主题反复尝试。
        if (
            isinstance(fallback_result, str)
            and fallback_result.upper() == HITLDecision.REJECTED.value
        ):
            resource_path = authorization.get("resource_path", "")
            action = authorization.get("action", "read")
            # 拒绝即判死（防 ping-pong）：把拒绝落库，authorization_gate 查询后
            # 对同线程同资源的后续访问直接硬拒绝，不再重复弹审批打扰用户。
            # 拒绝覆盖该调用的全部路径候选，避免逐路径 ping-pong。
            if thread_id:
                reject_targets = list(dict.fromkeys([(resource_path, action)] + all_paths))
                for r_path, _r_action in reject_targets:
                    try:
                        await HITLOrchestrator.mark_thread_resource_rejected(
                            thread_id=thread_id, resource_path=r_path
                        )
                    except Exception:
                        logger.exception(
                            "[HITL] mark_thread_resource_rejected failed (thread=%s, path=%s)",
                            thread_id,
                            r_path,
                        )
            return (
                f"[AUTHORIZATION REJECTED] 用户拒绝了工具 {tool_name or ''} "
                f"对 {resource_path} 的 {action} 访问。该操作未执行；"
                "请勿重试或换相近方式规避授权，应停止该操作并向用户说明。"
            )

        # 落库项目以审批创建端声明的 project_id 为准（宏确认已传 macro.project_id，
        # 保证 grant 与 AuthorizationService.is_granted 读取端同属一个授权域），
        # 缺失时回退会话项目。
        project_id = (
            authorization.get("project_id")
            or config.get("metadata", {}).get("project_id")
            or 0
        )
        from app.core.hitl.authorization import AuthorizationService

        # grant_mode（对齐 OpenCode reply allow/always/once）：
        #   "once"    → 仅本次，不持久化授权（等价 skip_grant）
        #   "always"  → 永久授权（expires_at=None）
        #   "default"/None → 普通授权维持 TTL grant；宏确认默认"每次执行"不持久化。
        # 宏（macro_run）只在用户显式选择 always 时才持久化，否则维持老行为（不写盘）。
        is_macro = authorization.get("action") == "macro_run"
        skip_grant = (
            bool(authorization.get("skip_grant"))
            or grant_mode == "once"
            or (is_macro and grant_mode != "always")
        )
        if not skip_grant:
            try:
                auth_service = AuthorizationService(project_id)
                # 作用域模型：grant_mode=dir → 授权父目录（prefix 递归命中），
                # 否则精确路径。always → 无 TTL；default → 7 天 TTL。
                if grant_mode == "dir":
                    grant_targets = [
                        (os.path.dirname(p) or p, a, "prefix")
                        for p, a in dict.fromkeys(all_paths)
                    ]
                else:
                    grant_targets = [
                        (p, a, "exact") for p, a in dict.fromkeys(all_paths)
                    ]
                for g_path, g_action, g_scope in grant_targets:
                    await auth_service.grant_permission(
                        resource_path=g_path,
                        action=g_action,
                        scope_type=g_scope,
                        granted_by=DEFAULT_GRANTED_BY,
                        ttl_days=None if grant_mode == "always" else DEFAULT_AUTHORIZATION_TTL_DAYS,
                    )
            except Exception as e:
                logger.warning(f"[HITL] grant_permission failed for approval: {e}")

        # 门控豁免声明（resume_override，由发起端在请求元数据中声明）：
        # 批准后重执行时按声明注入 args 标记，避免再次触发确认形成死循环
        # （宏确认注入 skip_confirmation 参数）。不在编排层按工具名特判。
        resume = pending_tool.get("resume") or {}
        args_override = resume.get("args") or {}
        if args_override:
            tool_args = {**tool_args, **args_override}

        # 重执行的门控放行是 DB 认领：finalize 已把该 call 的双轨定局为
        # COMPLETED+APPROVED，门控经 was_call_recently_approved 查询放行
        # （跨进程、重启成立），无需进程内标记。

        try:
            return await get_runtime().execute_tool(
                tool_name=tool_name,
                tool_args=tool_args,
                tool_call_id=tool_call_id,
                config=config,
                state=state,
            )
        except Exception as e:
            logger.exception(f"[HITL] Re-execution failed for {tool_name}: {e}")
            return f"[HITL Re-execution Failed] {e}"

    @staticmethod
    async def mark_thread_resource_rejected(thread_id: str, resource_path: str) -> None:
        """把本线程对某资源的待审批请求标记为已拒绝（拒绝即判死的数据源）。

        authorization_gate 在发起新审批前查询此标记：同线程同资源已被用户
        拒绝过的，后续访问直接硬拒绝，不再重复弹审批（防 ping-pong）。
        终态语义：
        - 匹配走 resource_path 列的**精确归一化路径相等**，禁止文本子串匹配；
        - 拒绝带 TTL（REJECTION_TTL_HOURS）：误拒不会永久 poison 线程；
        - 历史遗留的 pending 行一并关闭（用户已表达拒绝，不再需要响应）。
        """
        from datetime import timedelta

        from sqlalchemy import update

        from app.core.hitl.constants import REJECTION_TTL_HOURS
        from app.models import HumanRequest

        expires_at = utcnow() + timedelta(hours=REJECTION_TTL_HOURS)
        async with session_scope() as session:
            # pending 行：一并判死收口（用户已拒绝，不再等待响应）
            await session.execute(
                update(HumanRequest)
                .where(
                    HumanRequest.thread_id == thread_id,
                    HumanRequest.type == HumanRequestType.APPROVAL.value,
                    HumanRequest.status == HITLRequestStatus.PENDING.value,
                    HumanRequest.resource_path == resource_path,
                )
                .values(
                    status=HITLRequestStatus.COMPLETED.value,
                    result=HITLDecision.REJECTED.value,
                    resource_path=resource_path,
                    expires_at=expires_at,
                )
            )
            # 判死记录：结构化列 + TTL。已有同 key 判死行时续期即可，
            # 否则插入台账行（一次审批只对应一行 HumanRequest，复合命令的
            # 其余路径没有自己的请求行——台账行是判死的结构化数据源）。
            renewed = await session.execute(
                update(HumanRequest)
                .where(
                    HumanRequest.thread_id == thread_id,
                    HumanRequest.type == HumanRequestType.APPROVAL.value,
                    HumanRequest.result == HITLDecision.REJECTED.value,
                    HumanRequest.resource_path == resource_path,
                )
                .values(expires_at=expires_at, updated_at=utcnow())
            )
            if not renewed.rowcount:
                session.add(
                    HumanRequest(
                        id=gen_uuid(),
                        thread_id=thread_id,
                        type=HumanRequestType.APPROVAL.value,
                        description=f"[authorization rejected] {resource_path}",
                        status=HITLRequestStatus.COMPLETED.value,
                        result=HITLDecision.REJECTED.value,
                        resource_path=resource_path,
                        expires_at=expires_at,
                    )
                )

    @staticmethod
    async def has_thread_resource_rejection(thread_id: str, resource_path: str) -> bool:
        """查询本线程是否已有对某资源的有效拒绝记录（gate 判死查询）。

        结构化列精确匹配 + TTL 过滤：拒绝记录过期后返回 False，
        gate 会重新走 HITL（误拒的自动解封出口）。
        """
        if not thread_id or not resource_path:
            return False

        from sqlalchemy import select

        from app.models import HumanRequest

        async with session_scope() as session:
            stmt = (
                select(HumanRequest.id)
                .where(
                    HumanRequest.thread_id == thread_id,
                    HumanRequest.type == HumanRequestType.APPROVAL.value,
                    HumanRequest.result == HITLDecision.REJECTED.value,
                    HumanRequest.resource_path == resource_path,
                    (HumanRequest.expires_at.is_(None)) | (HumanRequest.expires_at > utcnow()),
                )
                .limit(1)
            )
            found = (await session.execute(stmt)).scalars().first()
            return found is not None

    @staticmethod
    async def was_call_recently_approved(
        thread_id: str, tool_call_id: str, window_seconds: int | None = None
    ) -> bool:
        """该 tool_call 是否在窗口内被批准过（门控放行重执行的跨进程认领）。

        终态语义（替代进程内放行注册表）：
        - 数据源 = messages 轨的 hitl_request 行（tool_call_id 精确匹配、
          status=completed、窗口内更新）+ human_requests 轨的 APPROVED 结果，
          双轨原子定局由 finalize_request 保证，两轨读到即为已批准；
        - DB 共享存储 → API / Worker 双进程、重启后均成立；
        - 窗口由 RECENT_APPROVAL_WINDOW_SECONDS 约束（覆盖 resolve → 重执行
          的正常间隔），同一 call_id 之后的新调用拿全新 tool_call_id，
          不会命中此窗口。
        """
        if not thread_id or not tool_call_id:
            return False

        from datetime import timedelta

        from sqlalchemy import select

        from app.core.hitl.constants import (
            MESSAGE_CATEGORY_HITL_REQUEST,
            RECENT_APPROVAL_WINDOW_SECONDS,
        )
        from app.models import HumanRequest

        if window_seconds is None:
            window_seconds = RECENT_APPROVAL_WINDOW_SECONDS
        cutoff = utcnow() - timedelta(seconds=window_seconds)

        async with session_scope() as session:
            res = await session.execute(
                select(Message.meta_data).where(
                    Message.thread_id == thread_id,
                    Message.category == MESSAGE_CATEGORY_HITL_REQUEST,
                    Message.tool_call_id == tool_call_id,
                    Message.status == MessageStatus.COMPLETED.value,
                    Message.updated_at >= cutoff,
                )
            )
            for (meta,) in res.all():
                req_id = (meta or {}).get("hitl_request_id")
                if not req_id:
                    continue
                req = (
                    await session.execute(
                        select(HumanRequest).where(
                            HumanRequest.id == req_id,
                            HumanRequest.status == HITLRequestStatus.COMPLETED.value,
                            HumanRequest.result == HITLDecision.APPROVED.value,
                        )
                    )
                ).scalar_one_or_none()
                if req is not None:
                    return True
        return False

    @staticmethod
    async def request_authorization(
        thread_id: str,
        action_description: str,
        resource_path: str,
        risk_level: str,
        policy: dict,
        project_id: int | None = None,
        run_id: str | None = None,
        tool_call_id: str | None = None,
        parent_id: str | None = None,
        original_tool_name: str | None = None,
        original_tool_args: dict | None = None,
        action: str | None = None,
        extra_paths: list[tuple[str, str]] | None = None,
    ) -> HumanInputRequest:
        """
        Trigger an authorization-style HITL request.

        This method is intended to be called from the authorization gate hook, not
        from an explicit tool. It reuses the `approval` request type so the existing
        frontend UI (Approve/Reject) works without changes.

        ``extra_paths``：同一次工具调用的其余待授权 (path, action) 候选，批准后
        一次性全量授权（见 push_hitl_notification）。
        """
        from app.core.hitl.prompts import build_approval_context

        context = build_approval_context(
            action_description=action_description,
            risk_level=risk_level,
            resource_path=resource_path,
            policy_description=policy.get("description", ""),
        )

        request = await create_request(
            thread_id=thread_id,
            request_type=HumanRequestType.APPROVAL.value,
            prompt=action_description,
            context=context,
            default_value=HITLDecision.REJECTED.value,
            resource_path=resource_path,
            resource_action=action or (action_description.split(" ", 1)[0] if action_description else ""),
        )

        response_text = i18n.get(
            "domain_tools.human_input.approval_template",
            id=request.id,
            approval_context=context,
        )

        await push_hitl_notification(
            thread_id=thread_id,
            request=request,
            request_data={
                "type": HumanRequestType.APPROVAL.value,
                "prompt": action_description,
                "context": context,
                "default_value": HITLDecision.REJECTED.value,
                "risk_level": risk_level,
                "resource_path": resource_path,
                # 前端按钮判定标记：payload.resource_path 在场 = 授权门控请求，
                # 审批卡据此显示「授权父目录」（grant_mode=dir）。
                "payload": {
                    "resource_path": resource_path,
                    "action": action or (action_description.split(" ", 1)[0] if action_description else ""),
                },
            },
            project_id=project_id,
            run_id=run_id,
            tool_name="request_approval",
            tool_call_id=tool_call_id,
            parent_id=parent_id,
            original_tool_name=original_tool_name,
            original_tool_args=original_tool_args,
            resource_path=resource_path,
            # action 用规范值（如 "read"/"write"），而非本地化描述的首词——
            # 否则 grant 存的 action（如 "读取"）与授权钩子比对的规范 action（"read"）
            # 永不匹配，导致敏感路径批准后重执行再次触发审批 → 无限循环。
            action=action or (action_description.split(" ", 1)[0] if action_description else ""),
            extra_paths=extra_paths,
        )

        raise_hitl_interrupt(request.id, response_text)
        return request  # unreachable
