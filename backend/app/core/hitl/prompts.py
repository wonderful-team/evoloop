"""
HITL 展示层：风险格式化 + approval 上下文统一构建。

供所有 HITL 发起端（ask_human / ask_confirm / macro 确认 / 授权门控 /
MCP 写工具确认）复用，消除各处重复的 emoji/i18n/上下文组装逻辑。

注意：业务级风险等级（如 MCP ``[risk:T1]``）不走标准
low/medium/high/critical 的 i18n 文案，由调用方自行拼接。
"""

import logging
from typing import Any

from app.i18n.service import i18n

logger = logging.getLogger(__name__)

#: 标准风险等级 → emoji（与前端 HumanRequestCard 展示一致）
RISK_EMOJI = {
    "low": "🟢",
    "medium": "🟡",
    "high": "🟠",
    "critical": "🔴",
}


def format_risk_header(risk_level: str) -> str:
    """返回统一的风险段，如 ``🟡 风险等级：中``。

    标准等级（low/medium/high/critical）走 i18n；未知等级回退为大写原文
    （如 ``⚪ 风险等级：T1``，供业务等级透传）。
    """
    emoji = RISK_EMOJI.get(risk_level, "⚪")
    localized = i18n.get(f"common.risk_levels.{risk_level}", default=risk_level.upper())
    return f"{emoji} {i18n.get('common.risk_levels.label', level=localized)}"


def resolve_tool_context() -> dict[str, Any]:
    """从当前 EvoContext 提取工具发起 HITL 所需的上下文字段。

    统一 ask_human / ask_confirm / run_macro 确认重复的 ctx 读取。
    缺少 thread_id 时抛 ValueError（fail-fast，HITL 必须在会话上下文内发起）。
    """
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    if not ctx.thread_id:
        raise ValueError("HITL tool requires a thread_id in the current EvoContext")
    return {
        "thread_id": ctx.thread_id,
        "project_id": ctx.project_id,
        "command_id": ctx.command_id,
        "tool_call_id": ctx.current_tool_call_id,
        "parent_id": ctx.last_ai_message_id,
    }


def build_approval_context(
    *,
    action_description: str,
    risk_level: str | None = None,
    details: str | None = None,
    consequences: str | None = None,
    resource_path: str | None = None,
    policy_description: str | None = None,
    extra_lines: list[str] | None = None,
) -> str:
    """统一构建 approval 上下文字符串（展示给运营人员/用户）。

    组装顺序：风险段 → 操作 → 资源 → 详情 → 后果 → 策略说明 → 自定义行。
    各段按传入与否选择性加入，未提供的段落不会出现占位空行。
    """
    lines: list[str] = []
    if risk_level:
        lines.append(format_risk_header(risk_level))
    lines.append(i18n.get("domain_tools.human_input.action", action=action_description))
    if resource_path:
        lines.append(
            i18n.get(
                "domain_tools.human_input.authorization.resource", path=resource_path
            )
        )
    if details:
        lines.append(i18n.get("domain_tools.human_input.details", details=details))
    if consequences:
        lines.append(
            i18n.get("domain_tools.human_input.consequences", conseq=consequences)
        )
    if policy_description:
        lines.append(policy_description)
    if extra_lines:
        lines.extend(extra_lines)
    return "\n\n".join(lines)
