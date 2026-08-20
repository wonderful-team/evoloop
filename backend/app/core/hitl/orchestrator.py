"""
HITL orchestrator: detection, normalization, state closure, and authorization.

Previously located in app.core.engine.hitl.
"""

import json
import logging

from app.core.engine.message.repository import MessageRepository
from app.core.hitl.batch_grants import approve_grant_by_request_id, reject_grant_by_request_id
from app.core.hitl.core import (
    HumanInputRequest,
    create_request,
    push_hitl_notification,
    raise_hitl_interrupt,
)
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


async def get_pending_hitl_call(config: dict) -> dict | None:
    """
    Detects a pending HITL request from the Message table.
    Returns the tool_call dictionary if found, otherwise None.
    """
    try:
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            from sqlalchemy import select

            from app.infrastructure.database import session_scope
            from app.models import Message

            async with session_scope() as session:
                stmt = (
                    select(Message)
                    .where(
                        Message.thread_id == thread_id,
                        Message.role == "system",
                        Message.category == "hitl_request",
                        Message.status == "waiting_human",
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
    {"text", "choice", "project_switch", "file_select"}
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
    if request_type in ("confirmation", "approval"):
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
        is_approval = bool(tool_call.get("authorization")) or name in ("ask_confirm", "request_approval")

    if not is_approval:
        # 自由文本类型：原样返回（含空输入——文本输入可能合法为空）
        return user_input if user_input is not None else ""

    if not user_input or not user_input.strip():
        return "REJECTED"  # Fail-safe: no explicit input = no approval

    lower_input = user_input.lower().strip()

    # Universal approval/rejection normalization (covers authorization-style HITL
    # where the original blocked tool name is not a standard HITL tool).
    if lower_input in _APPROVAL_SYNONYMS:
        return "APPROVED"
    if lower_input in _REJECTION_SYNONYMS:
        return "REJECTED"

    return user_input


async def close_hitl_message(
    thread_id: str, tool_call_id: str, status: str = "completed"
) -> None:
    """
    Update the status of the HITL request message in the database (single-track).

    Unlike ``finalize_request`` (which atomically updates both the
    ``human_requests`` and ``messages`` tracks), this only closes the message
    track. Used by the A2A callback path which never created a human_request
    row (its HITL request came from ``send_agent_task``).
    """
    try:
        repo = MessageRepository(thread_id=thread_id)
        success = await repo.update_status_by_tool_call_id(tool_call_id, status)
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
            request_type="approval",
            prompt=prompt,
            context=context,
            default_value="REJECTED",
        )

        if response_text_factory is not None:
            response_text = response_text_factory(request)
        elif response_template:
            # 不能直接 .format()：宏名/指令可能含 {query} 等花括号模板，
            # str.format 会误当占位符抛 KeyError（如宏『完成退款{query}』）。
            # 只精确替换 {id}/{prompt}，其它花括号原样保留。
            response_text = response_template.replace("{id}", request.id).replace("{prompt}", prompt)
        else:
            response_text = i18n.get("hitl.approval_default", id=request.id)

        await push_hitl_notification(
            thread_id=thread_id,
            request=request,
            request_data={
                "id": request.id,
                "type": "approval",
                "prompt": prompt,
                "context": context,
                "default_value": "REJECTED",
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
        thread_id: str, tool_call: dict, user_input: str | None
    ) -> str:
        """Processes resume logic: normalization, atomic dual-track closure, activity cleanup."""
        from app.core.hitl.core import finalize_request
        from app.core.monitoring.activity import activity_monitor

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
        await finalize_request(
            thread_id=thread_id,
            request_id=request_id,
            tool_call_id=tool_call["id"],
            status="completed",
            response=normalized,
            sibling_key=sibling_key,
        )
        await activity_monitor.clear_human_request(thread_id)
        return normalized

    @staticmethod
    async def handle_cancel(thread_id: str, tool_call: dict) -> str:
        """Processes cancellation logic: atomic dual-track closure, activity cleanup."""
        from app.core.hitl.core import finalize_request
        from app.core.monitoring.activity import activity_monitor

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
            status="cancelled",
            sibling_key=sibling_key,
        )
        await activity_monitor.clear_human_request(thread_id)
        return "CANCELLED"

    @staticmethod
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
        """
        from app.core.engine.message.repository import MessageRepository

        repo = MessageRepository(thread_id, project_id, member_id=member_id)
        if user_content:
            msg_id, seq = await repo.persist(
                role="human",
                content=user_content,
                category="user",
                action_type="text",
                status="completed",
            )
            # 实时推送到当前会话渠道（SSE 等）：与 persist_user_message 一致，
            # 否则 human 消息只落库、SSE 流收不到（前端仅历史加载才显示）。
            if msg_id:
                from app.core.engine.message.factory import MessageBlockFactory
                from app.core.engine.message.publisher import MessagePublisher

                block = MessageBlockFactory.from_event(
                    thread_id=thread_id,
                    sequence_number=seq,
                    role="human",
                    content=user_content,
                    category="user",
                    status="completed",
                    message_id=msg_id,
                )
                publisher = MessagePublisher(thread_id=thread_id, project_id=project_id)
                await publisher.publish(block)
        # 只更新 role='tool' 的结果消息（避免误改同 tool_call_id 的 hitl_request）
        await repo.update_tool_result_by_tool_call_id(tool_call_id, final_result)

    @staticmethod
    async def resume_and_persist(
        thread_id: str,
        project_id: int | None,
        member_id: int,
        config: dict,
        user_input: str | None,
        state=None,
    ) -> bool:
        """统一的后台/会话恢复路径：检测 → 关闭请求 → 审批重执行 → 持久化。

        供 ``runner.py``（voice/background）与 ``session.py``（会话模式）复用，
        消除两处几乎相同的 "handle_resume + resolve_approved_tool_result +
        repo.persist" 重复逻辑。返回是否确实消费了 pending 请求。

        注意：``_chat.py`` 的单发（无会话）路径刻意不走这里——它把工具结果写回
        ``inputs`` 交给 graph，而非独立 persist。
        """
        pending_tool = await HITLOrchestrator.get_pending_request(
            thread_id, (config.get("configurable") or {}).get("model")
        )
        if not pending_tool:
            return False
        normalized_input = await HITLOrchestrator.handle_resume(
            thread_id, pending_tool, user_input
        )
        final_result = await HITLOrchestrator.resolve_approved_tool_result(
            pending_tool, config, normalized_input, state=state
        )
        # 落为 human 消息（用户可见）+ 更新原 tool 消息结果（Agent 可见），
        # 而非新增 tool 消息（避免同 tool_call 双 tool 结果导致 Agent 取空）。
        await HITLOrchestrator.persist_hitl_user_message(
            thread_id=thread_id,
            project_id=project_id,
            member_id=member_id,
            tool_call_id=pending_tool["id"],
            user_content=normalized_input,
            final_result=final_result,
        )
        return True

    @staticmethod
    async def resolve_approved_tool_result(
        pending_tool: dict,
        config: dict,
        fallback_result: str,
        state=None,
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

        # 批量审批：请求参数携带 grant_id（ask_confirm 批量确认）时，批准后激活
        # 对应的 batch grant，拒绝则使其失效。数据驱动判定，不在编排层按工具名特判。
        grant_id = tool_args.get("grant_id")
        if grant_id:
            request_id = pending_tool.get("request_id")
            if (
                isinstance(fallback_result, str)
                and fallback_result.upper() == "APPROVED"
            ):
                grant = approve_grant_by_request_id(request_id) if request_id else None
                if grant:
                    return i18n.get(
                        "hitl.batch_approved",
                        grant_id=grant.id,
                        count=len(grant.operations),
                    )
                return i18n.get("hitl.batch_approved_fallback")
            if (
                isinstance(fallback_result, str)
                and fallback_result.upper() == "REJECTED"
            ):
                reject_grant_by_request_id(request_id)
                return i18n.get("hitl.batch_rejected")
            return fallback_result

        authorization = pending_tool.get("authorization")

        # 自由文本类型（无 authorization）：原样返回用户输入，不触发任何
        # APPROVED/REJECTED 判定——"REJECTED" 作为文本输入是合法内容。
        if not authorization:
            return fallback_result

        # 用户拒绝（授权门控）：不授权、不重执行，返回明确拒绝说明。
        if isinstance(fallback_result, str) and fallback_result.upper() == "REJECTED":
            resource_path = authorization.get("resource_path", "")
            return i18n.get("hitl.access_rejected", path=resource_path)

        project_id = config.get("metadata", {}).get("project_id") or 0
        from app.core.hitl.authorization import AuthorizationService

        # skip_grant 标记（如宏执行确认）：批准后仅重执行，不持久化授权——
        # 门控确认是"每次执行"语义，不应写入 project.json authorized_paths。
        if not authorization.get("skip_grant"):
            try:
                await AuthorizationService(project_id).grant_permission(
                    resource_path=authorization.get("resource_path", ""),
                    action=authorization.get("action", "read"),
                    granted_by="hitl-approval",
                )
            except Exception as e:
                logger.warning(f"[HITL] grant_permission failed for approval: {e}")

        if state is None:
            from app.core.engine.state import AgentState

            state = AgentState(
                thread_id=config.get("configurable", {}).get("thread_id"),
                project_id=project_id,
            )

        # 门控豁免声明（resume_override，由发起端在请求元数据中声明）：
        # 批准后重执行时按声明注入 args 标记，避免再次触发确认形成死循环
        # （宏确认注入 skip_confirmation 参数）。不在编排层按工具名特判。
        resume = pending_tool.get("resume") or {}
        args_override = resume.get("args") or {}
        if args_override:
            tool_args = {**tool_args, **args_override}

        try:
            from app.core.engine.tools.executor import AgentToolExecutor
            from app.core.tools.manager import tool_manager

            tool_map = {
                t.name: t for t in await tool_manager.get_node_tools("worker", state)
            }
            executor = AgentToolExecutor(
                tool_map=tool_map,
                state=state,
                config=config,
                name="HITLResume"
            )
            result = await executor.execute_tool(tool_name, tool_args, tool_call_id, [])
            return result.message.content or ""
        except Exception as e:
            logger.exception(f"[HITL] Re-execution failed for {tool_name}: {e}")
            return f"[HITL Re-execution Failed] {e}"

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
    ) -> HumanInputRequest:
        """
        Trigger an authorization-style HITL request.

        This method is intended to be called from the authorization gate hook, not
        from an explicit tool. It reuses the `approval` request type so the existing
        frontend UI (Approve/Reject) works without changes.
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
            request_type="approval",
            prompt=action_description,
            context=context,
            default_value="REJECTED",
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
                "type": "approval",
                "prompt": action_description,
                "context": context,
                "default_value": "REJECTED",
                "risk_level": risk_level,
                "resource_path": resource_path,
            },
            project_id=project_id,
            run_id=run_id,
            tool_name="request_approval",
            tool_call_id=tool_call_id,
            parent_id=parent_id,
            original_tool_name=original_tool_name,
            original_tool_args=original_tool_args,
            resource_path=resource_path,
            action=action_description.split(" ", 1)[0] if action_description else "",
        )

        raise_hitl_interrupt(request.id, response_text)
        return request  # unreachable
