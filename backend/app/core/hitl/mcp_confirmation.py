"""MCP write-tool confirmation gate.

对 MCP 写工具执行前做 HITL 确认（复用宏路径的 approval 链路），确认文案使用
工具 description 中的中文业务描述 + 本次参数，**不暴露 MCP 工具名/内部代码**，
面向运营人员可读。

门控判定：
- 工具名以 ``mcp__`` 开头（MCP 转换后的 EvoLoopTool）
- description 中含 ``[confirm:true]`` 元数据（商城侧已在工具 description 标注，
  见 ``handoff-write-operation-evoloop.md`` §2.1）

批准后经 resume 链路以原始工具名/参数重执行；重执行时通过 config 标记
``_skip_mcp_confirmation`` 跳过本门控，避免死循环。
"""

import logging
import re

from app.core.hitl import raise_hitl_interrupt
from app.core.hitl.prompts import resolve_tool_context

logger = logging.getLogger(__name__)

# 工具名匹配：mcp__server__tool 或 mcp__tool（不同连接形态）
_MCP_TOOL_PREFIX = "mcp__"


def is_mcp_tool(tool_name: str) -> bool:
    """判断工具是否为 MCP 转换工具。"""
    return bool(tool_name) and tool_name.startswith(_MCP_TOOL_PREFIX)


def parse_confirm_meta(description: str) -> tuple[bool, str, str]:
    """从工具 description 解析确认元数据。

    Returns:
        (confirm_required, business_description, risk_level)
        - confirm_required: ``[confirm:true]`` 是否出现
        - business_description: description 中的业务描述（去除元数据/参数段的首段）
        - risk_level: ``[risk:T?]`` 的原始值（如 "T1"），无则返回 ""
    """
    if not description:
        return False, "", ""

    # 提取风险等级 [risk:T?]
    risk_match = re.search(r"\[risk:\s*([A-Za-z0-9]+)\]", description)
    risk_level = risk_match.group(1) if risk_match else ""

    # 提取确认标记 [confirm:true/false]
    confirm_match = re.search(r"\[confirm:\s*(true|false)\]", description, re.IGNORECASE)
    confirm_required = bool(confirm_match) and confirm_match.group(1).lower() == "true"

    # 业务描述：去掉方括号元数据块、@param/@return 段后的首段可读文本
    cleaned = re.sub(r"\[[^\]]*\]", "", description)
    cleaned = re.sub(r"@param.*?$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"@return.*?$", "", cleaned, flags=re.MULTILINE)
    business_desc = cleaned.strip()

    return confirm_required, business_desc, risk_level


def _resolve_thread_id(config) -> str:
    if not config:
        return "default"
    cfgable = (
        config.get("configurable", {})
        if isinstance(config, dict)
        else getattr(config, "configurable", {})
    )
    return cfgable.get("thread_id", "default") or "default"


def _resolve_skip(config) -> bool:
    """检查 config 中的豁免标记（resume 重执行时注入）。"""
    if not config:
        return False
    return bool(config.get("_skip_mcp_confirmation"))


def _format_business_confirmation(
    business_desc: str, risk_level: str, tool_args: dict
) -> tuple[str, str]:
    """构造业务性确认文案（prompt + context），不暴露 MCP 工具名。

    从 tool_args 中挑选已知业务参数（order_goods_id/refund_no/order_no/goods_id/
    amount 等）拼入描述；无法识别时仅展示业务动作描述。
    """
    # 业务参数展示名（尽量用中文键）
    param_labels = {
        "order_goods_id": "订单项ID",
        "refund_no": "退款单号",
        "order_no": "订单号",
        "goods_id": "商品ID",
        "amount": "金额",
    }
    param_parts = []
    for key, label in param_labels.items():
        if key in tool_args and tool_args[key] not in (None, ""):
            param_parts.append(f"{label}={tool_args[key]}")

    # 首行作为 action 摘要（去掉句号/括号内的实现细节）
    first_line = (business_desc or "高风险写操作").splitlines()[0].strip()
    first_line = re.sub(r"[（(].*?[）)]", "", first_line).strip("。. ")
    if not first_line:
        first_line = "高风险写操作"

    action_description = f"{first_line}"
    if param_parts:
        action_description += f"（{'，'.join(param_parts)}）"

    risk_line = f"风险等级：{risk_level}" if risk_level else ""
    context_lines = [
        "该操作标记为需人工确认的高风险写操作（confirm:true）。",
        f"操作内容：{business_desc}",
    ]
    if param_parts:
        context_lines.append(f"操作对象：{'，'.join(param_parts)}")
    if risk_line:
        context_lines.append(risk_line)
    context_lines.append("请确认是否执行。")
    context = "\n".join(context_lines)

    return action_description, context


async def _find_pending_by_key(
    thread_id: str, tool_name: str, tool_args: dict
) -> dict | None:
    """查找同线程下同工具+同参数的已有 pending approval 请求。

    避免 Agent 重试同一写操作时产生重复 approval 请求（源头去重）：
    命中则复用已有请求（``hitl_request_id`` + ``context``），不创建新请求。

    Returns:
        ``{"request_id": ..., "context": ...}`` 或 None。
    """
    try:
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
            for msg in res.scalars().all():
                meta = msg.meta_data or {}
                original = meta.get("original_tool") or {}
                if original.get("name") != tool_name:
                    continue
                if (original.get("args") or {}) != tool_args:
                    continue
                req_id = meta.get("hitl_request_id")
                if req_id:
                    return {
                        "request_id": req_id,
                        "context": meta.get("hitl_context") or "",
                    }
    except Exception as e:
        logger.warning(f"[MCP Confirmation] Failed to find pending by key: {e}", exc_info=True)
    return None


async def find_recently_approved_by_key(
    thread_id: str, tool_name: str, tool_args: dict, window_seconds: int = 300
) -> str | None:
    """查找同线程下同工具+同参数**最近已批准**的请求。

    防止 Agent/LLM 在批准后因未收到结束信号而反复发起同一写操作（Supervisor
    循环调用 run_macro），每次循环都产生新的 approval 请求。若同 key 在窗口内
    已批准（completed），视为"已确认过"，返回该请求 ID 供调用方复用批准语义。

    Returns:
        最近已批准请求的 request_id，或 None。
    """
    try:
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        from app.infrastructure.database import session_scope
        from app.models import Message

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        async with session_scope() as session:
            stmt = (
                select(Message)
                .where(
                    Message.thread_id == thread_id,
                    Message.role == "system",
                    Message.category == "hitl_request",
                    Message.status.in_(["completed"]),
                    Message.updated_at >= cutoff,
                )
                .order_by(Message.updated_at.desc())
            )
            res = await session.execute(stmt)
            for msg in res.scalars().all():
                meta = msg.meta_data or {}
                original = meta.get("original_tool") or {}
                if original.get("name") != tool_name:
                    continue
                if (original.get("args") or {}) != tool_args:
                    continue
                req_id = meta.get("hitl_request_id")
                if req_id:
                    logger.info(
                        "[MCP Confirmation] Reusing recently approved request=%s for %s (thread=%s)",
                        req_id, tool_name, thread_id,
                    )
                    return req_id
    except Exception as e:
        logger.warning(f"[MCP Confirmation] Failed to find recently approved by key: {e}", exc_info=True)
    return None


async def _request_mcp_confirmation(
    tool_name: str,
    business_desc: str,
    risk_level: str,
    tool_args: dict,
    thread_id: str,
) -> str:
    """发起 MCP 写工具执行确认（approval 请求），批准后经 resume 重执行。

    源头去重：同线程下同工具+同参数已有 pending 请求时，复用该请求
    （不创建新请求、不重复推送），直接挂起等运营批准。
    """
    ctx_fields = resolve_tool_context()
    project_id = ctx_fields["project_id"]
    command_id = ctx_fields["command_id"]
    current_tool_call_id = ctx_fields["tool_call_id"]
    last_ai_message_id = ctx_fields["parent_id"]

    action_description, context = _format_business_confirmation(
        business_desc, risk_level, tool_args
    )

    # 源头去重：复用已有 pending 请求，避免运营看到重复 approval。
    existing = await _find_pending_by_key(thread_id, tool_name, tool_args)
    if existing:
        logger.info(
            "[MCP Confirmation] Reusing existing pending request=%s for %s (thread=%s)",
            existing["request_id"], tool_name, thread_id,
        )
        response_text = (
            f"该高风险写操作已有待确认请求（请求 ID: {existing['request_id']}），"
            "正在等待运营人员确认，已暂停。"
        )
        raise_hitl_interrupt(existing["request_id"], response_text)
        return response_text  # unreachable

    # 循环重试去重：同工具同参数最近已批准（窗口内 completed）时，不再创建新的
    # approval 请求——Agent 在批准后若反复发起同一写操作，复用已批准语义。
    recently_approved = await find_recently_approved_by_key(
        thread_id, tool_name, tool_args
    )
    if recently_approved:
        logger.info(
            "[MCP Confirmation] Skipping repeat confirmation for %s (thread=%s), "
            "recently approved=%s",
            tool_name, thread_id, recently_approved,
        )
        return (
            f"该高风险写操作已在请求 {recently_approved} 确认过，"
            "不再重复确认。"
        )

    from app.core.hitl.orchestrator import HITLOrchestrator

    response_template = (
        "该高风险写操作需要运营人员确认后才可执行（请求 ID: {id}）。"
        "已暂停等待确认。"
    )
    logger.info(
        "[MCP Confirmation] Confirmation requested for %s", tool_name,
    )
    # 统一发起 approval（create + push + raise），携带 skip_grant（不持久化授权）
    return await HITLOrchestrator.raise_approval(
        thread_id=thread_id,
        prompt=action_description,
        context=context,
        tool_name=tool_name,
        risk_level=risk_level or "high",
        tool_call_id=current_tool_call_id,
        parent_id=last_ai_message_id,
        project_id=project_id,
        run_id=str(command_id) if command_id else None,
        original_tool_name=tool_name,
        original_tool_args=tool_args,
        skip_grant=True,
        response_template=response_template,
    )


async def maybe_gate_mcp_tool(
    tool_name: str, description: str, tool_args: dict, config: dict | None
) -> None:
    """MCP 写工具确认门控入口。

    在 ``ToolExecutor.execute`` 中工具执行前调用。若工具是 MCP 工具且
    description 标注 ``[confirm:true]`` 且未豁免，则触发 HITL 确认
    （抛 interrupt 挂起，等待运营批准）。

    豁免条件：
    - config 中 ``_skip_mcp_confirmation=True``（resume 批准后重执行时注入）
    - description 未标注 confirm:true（低风险写工具直通）
    """
    if not is_mcp_tool(tool_name):
        return
    if _resolve_skip(config):
        return

    confirm_required, business_desc, risk_level = parse_confirm_meta(description)
    if not confirm_required:
        return

    thread_id = _resolve_thread_id(config)
    await _request_mcp_confirmation(
        tool_name, business_desc, risk_level, tool_args, thread_id
    )
